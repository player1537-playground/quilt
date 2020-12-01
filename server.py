#!/usr/bin/env python3.7
"""

"""

from __future__ import annotations
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from subprocess import Popen, PIPE
from dataclasses import dataclass
from io import BytesIO
from threading import Lock
from math import sqrt
from pathlib import Path
from typing import NewType
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, as_completed
from dns.resolver import Resolver
from PIL import Image
import requests


_g_subprocess: Subprocess = None
_g_buffers: Buffers = None
_g_service_name: str = None
_g_port: int = None

UUID = NewType('UUID', str)


@dataclass
class Subprocess:
	process: Popen
	lock: Lock
	
	@classmethod
	def create(cls, exe, *, env=None):
		# In order to read from the subprocess, it seems like
		# we need to read from either stdout or stderr, and
		# can't read from an arbitrary file descriptor. One
		# way around this is to take the file descriptor we
		# want and turn it into stdout, and then save the old
		# stdout to stderr. We can't do that without the shell.
		process = Popen(['bash', '-c', f'{exe} 100>&1 1>&2'], stdin=PIPE, stdout=PIPE, env=env)
		lock = Lock()
		return cls(process, lock)
	
	def submit(self, request: bytes):
		self.process.stdin.write(request + b'\n')
		self.process.stdin.flush()
	
	def receive(self) -> bytes:
		data = b''
		while True:
			data += self.process.stdout.read(1)
			if b':' in data:
				break
		
		length, rest = data.split(b':')
		length = int(length)
		
		data = self.process.stdout.read(length - len(rest))
		assert len(rest) + len(data) == length, f'{len(rest)}, {len(data)}, {length}'
		comma = self.process.stdout.read(1)  # comma
		assert comma == b',', f'Comma is {comma!r}'
		return rest + data


@dataclass
class Buffer:
	id: UUID
	data: bytes

	def __post_init__(self):
		buffer = self.data
		print(buffer[0], buffer[1], buffer[2], buffer[3])


@dataclass
class Buffers:
	lookup: Dict[UUID, Buffer]

	@classmethod
	def create(cls) -> Buffers:
		lookup = {}
		return cls(lookup)
	
	def __contains__(self, id: UUID) -> bool:
		return id in self.lookup

	def __getitem__(self, id: UUID) -> Buffer:
		try:
			return self.lookup[id]
		except KeyError:
			buffer = self._request_from_others(id)
			self.lookup[id] = buffer
			return buffer
	
	def add(self, data: bytes) -> Buffer:
		id = str(uuid4())
		buffer = Buffer(id, data)
		self.lookup[id] = buffer
		return buffer
	
	@staticmethod
	def _make_request(host: str, id: UUID) -> requests.Request:
		with requests.get(f'http://{host}:{_g_port}/buffer/{id}') as r:
			r.raise_for_status()
			return r.content

	def _request_from_others(self, id: UUID) -> Buffer:
		if _g_service_name is None:
			raise NotImplementedError

		print(f'Asking other hosts for {id}')

		resolver = Resolver()
		hosts = []
		for answer in resolver.query(f'tasks.{_g_service_name}.'):
			answer = str(answer)
			hosts.append(answer)
		
		print(f'Got hosts: {hosts!r}')

		executor = ThreadPoolExecutor(max_workers=len(hosts))
		futures = []
		for host in hosts:
			future = executor.submit(self._make_request, host, id)
			futures.append(future)

		for future in as_completed(futures):
			try:
				data = future.result()
			except:
				continue
			else:
				break

		for future in futures:
			future.cancel()

		print(f'Done! Buffer = ', data[0], data[1], data[2], data[3])
		return Buffer(id, data)


class RequestHandler(SimpleHTTPRequestHandler):
	protocol_version = 'HTTP/1.1'

	def do_GET(self):
		if self.path == '/':
			self.directory = 'static'
			super().do_GET()
		elif self.path == '/favicon.ico':
			super().do_GET()
		elif self.path.startswith('/static/'):
			super().do_GET()
		elif self.path.startswith('/image/'):
			self.do_GET_image()
		elif self.path.startswith('/buffer/'):
			self.do_GET_buffer()
		else:
			raise NotImplementedError
	
	def do_GET_image(self):
		_, image, what, x, y, z, ux, uy, uz, vx, vy, vz, quality, optstring = self.path.split('/')
		assert _ == '', f'{_!r} is not empty'
		assert image == 'image'
		x, y, z = map(float, (x, y, z))
		ux, uy, uz = map(float, (ux, uy, uz))
		vx, vy, vz = map(float, (vx, vy, vz))
		quality = int(quality)

		sx, sy, sz, sR = [], [], [], []
		sr, sg, sb = [], [], []

		trivert, trinorm, triuv, triindex = [], [], [], []
		trir, trig, trib = [], [], []
		
		it = iter(what.split(','))
		type = next(it)
		if type == 'scene':
			for k in it:
				if k == 'sphere':
					sx.append(float(next(it)))
					sy.append(float(next(it)))
					sz.append(float(next(it)))
					sR.append(float(next(it)))
					sr.append(float(next(it)))
					sg.append(float(next(it)))
					sb.append(float(next(it)))
				elif k == 'triangles':
					trivert.append(_g_buffers[next(it)])
					trinorm.append(_g_buffers[next(it)])
					triuv.append(_g_buffers[next(it)])
					triindex.append(_g_buffers[next(it)])
					trir.append(float(next(it)))
					trig.append(float(next(it)))
					trib.append(float(next(it)))
				else:
					print(f'bad scene type {k!r}')
					raise NotImplementedError
		else:
			print(f'bad type {scene!r}')
			raise NotImplementedError

		options = {}
		it = iter(optstring.split(','))
		for k, v in zip(it, it):
			options[k] = v

		tiling = options.get('tiling', '0-1')
		tile_index, num_tiles = tiling.split('-')
		tile_index = int(tile_index)
		bgcolor = tuple(map(int, options.get('bgcolor', '255-255-255-255').split('-')))
		num_tiles = int(num_tiles)
		n_cols = int(sqrt(num_tiles))

		tile_quality = int(quality // n_cols)
		
		query = (
			b'%f %f %f %f %f %f %f %f %f %d %d %d '
			b'%d %s '
			b'%d %s '
		) % (
			x, y, z, ux, uy, uz, vx, vy, vz, tile_quality, tile_index, n_cols,
			len(sx), b''.join(
				b'%f %f %f %f %f %f %f' % parts
				for parts in zip(sx, sy, sz, sR, sr, sg, sb)
			),
			len(trivert), b''.join(
				b''.join([
					b'%d %s ' % (len(trivert.data), trivert.data),
					b'%d %s ' % (len(trinorm.data), trinorm.data),
					b'%d %s ' % (len(triuv.data), triuv.data),
					b'%d %s ' % (len(triindex.data), triindex.data),
					b'%f %f %f ' % (trir, trig, trib),
				])
				for trivert, trinorm, triuv, triindex, trir, trig, trib in zip(trivert, trinorm, triuv, triindex, trir, trig, trib)
			),
		)
		
		with _g_subprocess.lock:
			_g_subprocess.submit(query)
			data = _g_subprocess.receive()
		
		if b'error' in data:
			print(data)

		image = Image.frombytes('RGBA', (tile_quality, tile_quality), data, 'raw', 'RGBA', 0, 1)
		canvas = Image.new('RGBA', image.size, bgcolor)
		canvas.paste(image, mask=image)
		buffer = BytesIO()
		canvas.save(buffer, 'PNG')
		
		content = buffer.getvalue()

		self.send('image/png', content)
	
	def do_GET_buffer(self):
		# GET /buffer/:id
		_, _, id = self.path.split('/')

		if id not in _g_buffers:
			self.send('text/plain', b'404', response=404)
		else:
			buffer = _g_buffers[id]
			self.send('application/octet-stream', buffer.data)
	
	def do_POST(self):
		length = self.headers['content-length']
		nbytes = int(length)
		data = self.rfile.read(nbytes)
		# throw away extra data? see Lib/http.server.py:1203-1204
		self.data = data

		if self.path == '/buffer/':
			self.do_POST_buffer()
		else:
			print('POST', self.path)
			raise NotImplementedError
	
	def do_POST_buffer(self):
		data = self.data
		buffer = _g_buffers.add(data)
		content = buffer.id.encode('utf-8')
		self.send('text/plain', content)
	
	def send(self, content_type, content, *, response=200):
		connection = self.headers['connection']
		keep_alive = False
		if connection == 'keep-alive':
			keep_alive = True
		
		self.send_response(response)
		self.send_header('Content-Type', content_type)
		self.send_header('Content-Length', str(len(content)))
		self.send_header('Access-Control-Allow-Origin', self.headers['origin'])
		if keep_alive:
			self.send_header('Connection', 'keep-alive')
		self.end_headers()
		self.wfile.write(content)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
	pass


def main(bind, port, exe, service_name):
	buffers = Buffers.create()

	env = {}

	subprocess = Subprocess.create(exe, env=env)
	
	global _g_subprocess
	_g_subprocess = subprocess

	global _g_buffers
	_g_buffers = buffers

	global _g_service_name
	_g_service_name = service_name

	global _g_port
	_g_port = port
	
	address = (bind, port)
	print(f'Listening on {address!r}')
	server = ThreadingHTTPServer(address, RequestHandler)
	server.serve_forever()


def cli():
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument('--port', type=int, default=8820)
	parser.add_argument('--bind', default='')
	parser.add_argument('--service-name')
	parser.add_argument('--exe', required=True)
	args = vars(parser.parse_args())

	main(**args)


if __name__ == '__main__':
	cli()

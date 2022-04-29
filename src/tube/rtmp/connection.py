"""RTMP protocol network connection"""
import secrets
from datetime import datetime
from enum import IntEnum
from typing import Union
from .chunk import CS0, CSn, Chunk, ChunkMessageHeader
from .messages.amf0 import Number, String
from .messages.command import Command, ResultCommand, OnBWDoneCommand
from .messages.control import SetChunkSize
from .messages.control import WindowAcknowledgementSize, SetPeerBandwidth, UserControlMessage

State: IntEnum = IntEnum('State', ('Initial',
                                   'Handshake'
                                   )
                         )


class ConnectionException(ValueError):
    """Exception, raised on connection errors"""
    pass


class Connection:
    """Manages RTMP protocol network connection activity"""
    @staticmethod
    def version():
        return 3

    def __init__(self, address, params):
        self._root: str = params.get("root", ".")
        self._verbal: bool = params.get("verb", False)
        self._address: str = address
        self._c1: CSn = CSn(0, 0, b'')
        self._s1: CSn = CSn(int(datetime.now().timestamp()), 0, secrets.token_bytes(1528))
        self._state: State = State.Initial
        self._chunk: Chunk = Chunk()
        print(f'RTMP connect from {self._address}')

    def on_read_event(self, key, buffer):
        """Manager read socket event"""
        if buffer:
            self._on_message(buffer, key.data)
            key.data.inb = b''
            return
        raise EOFError()

    def on_write_event(self, key):
        """Manager write socket event"""
        if key.data.outb:
            sent = key.fileobj.send(key.data.outb)  # Should be ready to write
            key.data.outb = key.data.outb[sent:]

    def _on_message(self, buffer, data):
        if not self._c1.random:
            self._on_c0(buffer, data)
        elif self._state == State.Initial and len(buffer) >= 1536:
            self._on_c2(buffer)
        else:
            self._chunk.parse(buffer, self._on_command, data)

    def _on_c0(self, buffer, data):
        c0: CS0 = CS0(buffer[0])
        if c0.version != Connection.version():
            raise ConnectionException(f'unsupported protocol version {c0.version}')
        self._c1 = CSn(int.from_bytes(buffer[1:5], byteorder='big'),
                       int.from_bytes(buffer[5:9], byteorder='big'),
                       buffer[9:])
        s0: bytes = Connection.version().to_bytes(1, 'big')
        s1: bytes = self._s1.time.to_bytes(4, 'big') + self._s1.time2.to_bytes(4, 'big') + self._s1.random
        s2: bytes = self._c1.time.to_bytes(4, 'big') + self._s1.time.to_bytes(4, 'big') + self._c1.random
        data.outb = s0 + s1 + s2

    def _on_c2(self, buffer):
        c2: CSn = CSn(int.from_bytes(buffer[0:4], byteorder='big'),
                      int.from_bytes(buffer[4:8], byteorder='big'),
                      buffer[8:])
        time_ok, time2_ok, random_ok = c2.time == self._s1.time,\
            c2.time2 == self._c1.time,\
            c2.random == self._s1.random
        if not (time_ok and time2_ok and random_ok):
            raise ConnectionException(f'Handshake failed: time {time_ok}, time2 {time2_ok} random {random_ok}')
        self._state = State.Handshake

    def _on_command(self, header: ChunkMessageHeader, data: bytes, out_data):
        print(header)
        for c in data:
            print(f'{c:x} ', end='')
        print(f'of {len(data)}')
        if header.message_type_id == SetChunkSize.type_id:
            self._chunk.size = SetChunkSize().from_bytes(data).chunk_size
            print(f'new chunk size={self._chunk.size}')
        elif header.message_type_id == Command.amf0_type_id:
            command: Union[Command, None] = Command.make(data, self._chunk.size)
            if command and command.type == 'connect':
                print(command)
                out_data.outb = WindowAcknowledgementSize().to_bytes() +\
                    SetPeerBandwidth().to_bytes() +\
                    UserControlMessage().to_bytes() +\
                    SetChunkSize().to_bytes() +\
                    ResultCommand(command.transaction_id, self._chunk.size,
                                  {
                                      'fmsVer': String('FMS/3,0,1,123'),
                                      'capabilities': Number(31.)
                                  },
                                  {
                                      'level': String('status'),
                                      'code': String('NetConnection.Connect.Success'),
                                      'description': String('Connection succeeded.'),
                                      'objectEncoding': Number(0.)
                                  }).to_bytes() +\
                    OnBWDoneCommand(0., self._chunk.size).to_bytes()
            elif command and command.type == 'releaseStream':
                print(command)
                out_data.outb = ResultCommand(command.transaction_id, self._chunk.size).to_bytes()

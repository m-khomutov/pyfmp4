class BoxIterator:
   def __init__(self, box):
       self._box = box
       self._index = 0

   def __next__(self):
       if self._index < len(self._box._storage):
           result = self._box._storage[self._index]
           self._index +=1
           return result
       raise StopIteration


class Box:
    def __init__(self, *args, **kwargs):
        self._user_type = []
        self._storage = []
        self._depth = 0
        self.position = 0
        file = kwargs.get("file", None)
        if file is not None:
            self._fromfile(file, kwargs.get("depth", None))
            return
        self.type = kwargs.get("type", None)
        self.size = 8

    def __repr__(self):
        ret = " " * (self._depth * 2) + \
              "%s pos:%i size:%i" % (self.type, self.position, self.fullsize())
        if len(self._user_type) == 16:
            ret += " user type:" + str(self._user_type)

        if type(self) is Box:
            for s in self._storage:
                ret += "\n" + s.__repr__()
        return ret

    def __str__(self):
        return self.__repr__()

    def __iter__(self):
        return BoxIterator(self)

    def store(self, box, parent_type=''):
        if parent_type == '':
            box._depth = self._depth + 2
            self._storage.append(box)
        else:
            parent = self.find(parent_type)
            if len(parent) > 0:
                parent[0].store(box)

    def find(self, searched_type):
        ret = []
        if searched_type == self.type:
            ret.append(self)
            return ret
        for box in self._storage:
            b = box.find(searched_type)
            for i in b:
                ret.append(i)
        return ret

    def container(self):
        return self.type == 'moov' or self.type == 'trak' or self.type == 'edts' or \
               self.type == 'mdia' or self.type == 'minf' or self.type == 'dinf' or \
               self.type == 'stbl' or self.type == 'mvex' or self.type == 'moof' or \
               self.type == 'traf'

    def depth(self):
        return self._depth

    def to_bytes(self):
        sz = self.fullsize()
        if sz >= 0xffffffff:
            ret = (1).to_bytes(4, byteorder='big')
        else:
            ret = sz.to_bytes(4, byteorder='big')
        ret += str.encode(self.type)
        if sz >= 0xffffffff:
            ret += sz.to_bytes(8, byteorder='big')
        if self.type == 'uuid':
            ret += self._user_type
        if type(self) is Box:
            for s in self._storage:
                ret += s.to_bytes()
        return ret

    def fullsize(self):
        ret = self.size
        for box in self._storage:
            ret += box.fullsize()
        return ret

    def _readsome(self, f, chunk):
        b = f.read(chunk)
        if len(b) == chunk:
            return b
        raise EOFError()

    def _fromfile(self, f, depth):
        self.position = f.tell()
        self.size = int.from_bytes(self._readsome(f, 4), "big")
        self.type = self._readsome(f, 4).decode("utf-8")
        if self.size == 1: int.from_bytes(self._readsome(f, 8), "big")
        if self.type == 'uuid': self._utype = self._readsome(f, 16)
        self._depth = depth


class FullBox(Box):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        file = kwargs.get("file", None)
        if file is not None:
            self.version = self._readsome(file, 1)[0]
            self.flags = int.from_bytes(self._readsome(file, 3), "big")
        else:
            self.version = kwargs.get("version", 0)
            self.flags = kwargs.get("flags", 0)
            self.size = 12

    def __repr__(self):
        ret = super().__repr__() + " version:" + str(self.version) + " flags:" + hex(self.flags)
        for s in self._storage:
            ret += "\n" + s.__repr__()
        return ret

    def to_bytes(self):
        ret = super().to_bytes()
        ret += self.version.to_bytes(1, byteorder='big')
        ret += self.flags.to_bytes(3, byteorder='big')
        return ret

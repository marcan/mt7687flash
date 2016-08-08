#!/usr/bin/python

# Copyright (c) 2016 Hector Martin <marcan@marcan.st>
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import print_function

import sys, os.path, struct, argparse
from xmodem import XMODEM
from serial import Serial

BIN_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "bin")

class MtkFlasher(object):
    BAUD = {
        "ls": 115200,
        "hs": 921600,
        "ss": 3000000,
    }
    MAGIC = 0x00052001

    def __init__(self, port, speed, binpath=None, debug=False):
        self.speed = speed
        self.baud = self.BAUD[speed]
        self.port = port
        self.xm = XMODEM(self.getc, self.putc, "xmodem1k", "\xff")
        self.binpath = binpath or BIN_PATH
        self.tag = 0x1000
        self.debug = debug

    def log(self, *args):
        if self.debug:
            print(*args)

    def getc(self, size, timeout=1):
        self.ser.timeout = timeout
        return self.ser.read(size)

    def putc(self, data, timeout=1):
        self.ser.write_timeout = timeout
        return self.ser.write(data)

    def xm_send(self, fd, msg="  Sending"):
        fd.seek(0, 2)
        length = fd.tell()
        fd.seek(0, 0)
        blocks = (length + 1023) / 1024

        def callback(total, success, error):
            sys.stdout.write("\r%s... %d%%" % (msg, 100 * success // blocks))
            sys.stdout.flush()

        self.xm.send(fd, callback=callback)
        print()

    def bootstrap(self, ):
        print("Opening port at 115200 baud...")
        self.ser = Serial(self.port, 115200)
        fname = "uart_%s.bin" % self.speed
        print("Sending baudrate switcher (%s)..." % fname)
        self.xm_send(open(os.path.join(self.binpath, fname), "rb"))
        self.ser.close()

        print("Reopening port at %d baud..." % self.baud)
        self.ser = Serial(self.port, self.baud)
        fname = "ated_%s.bin" % self.speed
        print("Sending ATED (%s)..." % fname)
        self.xm_send(open(os.path.join(self.binpath, fname), "rb"))

    def command(self, cmd, args=b""):
        self.tag += 1
        self.ser.timeout = 5
        self.ser.write_timeout = 5

        payload = struct.pack(">H", cmd) + args
        data = struct.pack(">IHH", 0x00052001,
                           len(payload) + 2, self.tag) + payload
        crc = self.xm.calc_crc(data)
        self.ser.write(data + struct.pack(">H", crc))

        reply = self.ser.read(8)
        magic, reply_len, tag = struct.unpack(">IHH", reply)
        assert magic == (self.MAGIC | 0x80000000)
        assert tag == self.tag
        reply += self.ser.read(reply_len)
        assert len(reply) == reply_len + 8
        crc = struct.unpack(">H", reply[-2:])[0]
        assert self.xm.calc_crc(reply[:-2]) == crc
        reply_cmd = struct.unpack(">H", reply[8:10])[0]
        assert reply_cmd == (cmd + 1)
        return reply[10:-2]

    def initialize(self):
        self.log("  cmd: initialize")
        reply = self.command(0x00)
        self.log("    returned:", reply.encode("hex"))

    def get_storage_info(self):
        self.log("  cmd: get_storage_info")
        reply = self.command(0x10)
        self.log("    returned:", reply.encode("hex"))

        unk1, unk2, flash_size, = struct.unpack(">III", reply)
        return {"size": flash_size}

    def erase(self, start, length):
        self.log("  cmd: erase(0x%x, 0x%x)" % (start, length))
        reply = self.command(0x0a, struct.pack(">II", start, length))
        self.log("    returned:", reply.encode("hex"))

    def erase_end(self):
        self.log("  cmd: erase_end")
        reply = self.command(0x0c)
        self.log("    returned:", reply.encode("hex"))

    def download(self, address, length):
        self.log("  cmd: download(0x%x, 0x%x)" % (address, length))
        flags = 0x01000400
        reply = self.command(0x02, struct.pack(">IIII",
                                               address, length,
                                               address + length, flags))
        self.log("    returned:", reply.encode("hex"))

    def download_end(self):
        self.log("  cmd: download_end")
        reply = self.command(0x04)
        self.log("    returned:", reply.encode("hex"))

    # Orig uses 0x20000 but this provides more granular progress
    def erase_range(self, addr, length, blocksize=0x2000):
        for i in xrange(0, length, blocksize):
            self.erase(addr + i, min(blocksize, length - i))
            if not self.debug:
                sys.stdout.write("\r  Erasing... %d%%" % (100 * i // length))
                sys.stdout.flush()
        self.erase_end()
        if not self.debug:
            print("\r  Erasing... 100%")

    def write_file(self, addr, filename, erase=True):
        print("Writing to 0x%x: %s" % (addr, filename))
        fd = open(filename, "rb")
        fd.seek(0, 2)
        length = fd.tell()
        fd.seek(0, 0)

        assert addr & 0xfff == 0
        padded_length = (length + 0xfff) & ~0xfff

        if erase:
            self.erase_range(addr, padded_length)

        self.download(addr, length)
        self.xm_send(fd, "  Writing")
        self.download_end()

if __name__ == "__main__":
    def parse_write(s):
        off, f = s.split(":", 1)
        off = int(off, 0)
        return off, f

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show debug output")
    parser.add_argument("-b", "--bin",
                        help="path to the directory containing flasher blobs")
    parser.add_argument("-p", "--port", metavar="PORT", default="/dev/ttyACM0",
                        help="serial port device")
    parser.add_argument("-s", "--speed", metavar="SPEED", default="hs",
                        help="port speed (ls|hs|ss)", choices=["ls","hs","ss"])
    parser.add_argument("-e", "--erase", action="store_true",
                        help="wipe the entire flash memory first")
    parser.add_argument("-w", "--write", metavar="ADDR:FILE", action="append",
                        help="write a file to flash memory", type=parse_write)

    args = parser.parse_args()

    mtk = MtkFlasher(args.port, args.speed, binpath=args.bin,
                     debug=args.verbose)

    mtk.bootstrap()
    mtk.initialize()
    info = mtk.get_storage_info()
    print("Flash size: 0x%x" % info["size"])

    if args.erase:
        print("Erasing flash memory...")
        mtk.erase_range(0, info["size"])

    if args.write:
        for off, filename in args.write:
            mtk.write_file(off, filename, erase=not args.erase)


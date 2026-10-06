"""Read PE32+ metadata without loading or executing the image.

This deliberately small reader supports offline compatibility checks for the
native adapter. It never guesses an address when a pattern is ambiguous.
"""
from dataclasses import dataclass
import re
import struct


@dataclass(frozen=True)
class Section:
    name: str
    rva: int
    virtual_size: int
    offset: int
    raw_size: int
    flags: int

    @property
    def executable(self):
        return bool(self.flags & 0x20000000)


class PEImage:
    def __init__(self, data: bytes):
        self.data = data
        if self.read(0, 2) != b"MZ":
            raise ValueError("Missing DOS signature")
        pe = self.unpack("I", 0x3c)[0]
        if self.read(pe, 4) != b"PE\0\0":
            raise ValueError("Missing PE signature")
        machine, count, self.timestamp = self.unpack("HHI", pe + 4)
        optional_size = self.unpack("H", pe + 20)[0]
        optional = pe + 24
        if machine != 0x8664 or optional_size < 144 or self.unpack("H", optional)[0] != 0x20b:
            raise ValueError("Expected an x64 PE32+ image")
        self.read(optional, optional_size)
        self.image_base = self.unpack("Q", optional + 24)[0]
        self.image_size = self.unpack("I", optional + 56)[0]
        if not 1 <= count <= 96 or self.image_size == 0:
            raise ValueError("Invalid section count or image size")
        self.sections = []
        for i in range(count):
            at = optional + optional_size + i * 40
            name = self.read(at, 8).rstrip(b"\0").decode("ascii", errors="strict")
            size, rva, raw_size, offset = self.unpack("IIII", at + 8)
            flags = self.unpack("I", at + 36)[0]
            self.read(offset, raw_size)
            if rva + max(size, raw_size) > self.image_size:
                raise ValueError("Section outside virtual image")
            self.sections.append(Section(name, rva, size, offset, raw_size, flags))
        for i, a in enumerate(self.sections):
            for b in self.sections[i + 1:]:
                if max(a.rva, b.rva) < min(a.rva + max(a.virtual_size, a.raw_size), b.rva + max(b.virtual_size, b.raw_size)):
                    raise ValueError("Overlapping virtual sections")
                if a.raw_size and b.raw_size and max(a.offset, b.offset) < min(a.offset + a.raw_size, b.offset + b.raw_size):
                    raise ValueError("Overlapping raw sections")
        directories = self.unpack("I", optional + 108)[0]
        if directories < 4:
            self.exception_rva, self.exception_size = 0, 0
        else:
            self.exception_rva, self.exception_size = self.unpack("II", optional + 112 + 3 * 8)

    def read(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError("Truncated PE data")
        return self.data[offset:offset + size]

    def unpack(self, fmt: str, offset: int):
        return struct.unpack("<" + fmt, self.read(offset, struct.calcsize("<" + fmt)))

    def section_at(self, rva: int, size: int = 1) -> Section:
        if size < 1:
            raise ValueError("Empty virtual read")
        for section in self.sections:
            if section.rva <= rva and rva + size <= section.rva + max(section.virtual_size, section.raw_size):
                return section
        raise ValueError(f"Unmapped RVA {rva:#x}")

    def at(self, rva: int, size: int) -> bytes:
        section = self.section_at(rva, size)
        relative = rva - section.rva
        if relative + size > section.raw_size:
            raise ValueError("RVA is virtual zero-fill, not file data")
        return self.read(section.offset + relative, size)

    def find(self, pattern: str) -> list[int]:
        tokens = pattern.split()
        if not tokens or all(t in {"?", "??"} for t in tokens):
            raise ValueError("Pattern must contain fixed bytes")
        parts = []
        for t in tokens:
            if t in {"?", "??"}:
                parts.append(b".")
            elif re.fullmatch("[0-9a-fA-F]{2}", t):
                parts.append(re.escape(bytes([int(t, 16)])))
            else:
                raise ValueError("Invalid byte pattern")
        # Lookahead counts overlapping matches too.
        regex = re.compile(b"(?=" + b"".join(parts) + b")", re.DOTALL)
        return [s.rva + m.start() for s in self.sections if s.executable
                for m in regex.finditer(self.read(s.offset, s.raw_size))]

    def unique(self, pattern: str) -> int:
        matches = self.find(pattern)
        if len(matches) != 1:
            raise ValueError(f"Expected one executable pattern match, got {len(matches)}")
        return matches[0]

    def rip_target(self, instruction: int, displacement: int, length: int) -> int:
        if not 0 <= displacement <= length - 4 or length > 15:
            raise ValueError("Invalid RIP displacement field")
        raw = self.at(instruction, length)
        target = instruction + length + struct.unpack_from("<i", raw, displacement)[0]
        self.section_at(target)
        return target

    def functions(self) -> list[tuple[int, int, int]]:
        if not self.exception_size:
            return []
        if self.exception_size % 12:
            raise ValueError("Malformed x64 exception directory")
        result = list(struct.iter_unpack("<III", self.at(self.exception_rva, self.exception_size)))
        previous = 0
        for begin, end, unwind in result:
            if not begin < end or begin < previous or not self.section_at(begin, end - begin).executable:
                raise ValueError("Malformed runtime function range")
            self.section_at(unwind)
            previous = end
        return result

    def function_at(self, rva: int) -> tuple[int, int, int]:
        matches = [f for f in self.functions() if f[0] <= rva < f[1]]
        if len(matches) != 1:
            raise ValueError("No unique runtime function for address")
        return matches[0]

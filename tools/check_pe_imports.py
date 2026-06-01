"""Dump the DLL import table of a PE file (no Visual Studio required)."""

import struct
import sys


def get_pe_imports(path: str):
    """Return list of (dll_name, str) from the IMPORT_DIRECTORY of a PE.

    Minimal PE parser: dos header -> nt header -> optional header ->
    data directory[1] (IMPORT). We follow the descriptors until the
    Name field is 0 and read each Name as ASCII at its RVA.
    """
    with open(path, "rb") as f:
        data = f.read()

    if data[:2] != b"MZ":
        raise ValueError("Not a PE file")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        raise ValueError("Bad PE signature")

    coff = e_lfanew + 4
    machine = struct.unpack_from("<H", data, coff)[0]
    number_of_sections = struct.unpack_from("<H", data, coff + 2)[0]
    size_of_opt_header = struct.unpack_from("<H", data, coff + 16)[0]
    opt_off = coff + 20
    magic = struct.unpack_from("<H", data, opt_off)[0]
    if magic == 0x10B:        # PE32
        data_dir_off = opt_off + 96
    elif magic == 0x20B:      # PE32+
        data_dir_off = opt_off + 112
    else:
        raise ValueError(f"Unknown PE optional-header magic 0x{magic:x}")

    import_rva = struct.unpack_from("<I", data, data_dir_off + 8)[0]
    import_size = struct.unpack_from("<I", data, data_dir_off + 12)[0]
    if import_rva == 0 or import_size == 0:
        return []

    # Build sections to translate RVA -> file offset.
    sec_off = opt_off + size_of_opt_header
    sections = []
    for i in range(number_of_sections):
        s = sec_off + 40 * i
        virt_size = struct.unpack_from("<I", data, s + 8)[0]
        virt_addr = struct.unpack_from("<I", data, s + 12)[0]
        raw_size  = struct.unpack_from("<I", data, s + 16)[0]
        raw_off   = struct.unpack_from("<I", data, s + 20)[0]
        sections.append((virt_addr, max(virt_size, raw_size), raw_off))

    def rva_to_off(rva: int) -> int:
        for v, vs, r in sections:
            if v <= rva < v + vs:
                return rva - v + r
        return -1

    out = []
    import_off = rva_to_off(import_rva)
    if import_off < 0:
        return []
    descriptor = import_off
    while True:
        name_rva = struct.unpack_from("<I", data, descriptor + 12)[0]
        if name_rva == 0:
            break
        name_off = rva_to_off(name_rva)
        end = data.index(b"\0", name_off)
        out.append(data[name_off:end].decode("ascii", errors="replace"))
        descriptor += 20
    return out


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(f"=== {arg} ===")
        try:
            for dll in get_pe_imports(arg):
                print(f"  {dll}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
        print()

"""Check native publish's gates against the actual pinned PE, without execution."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools/debug-python'))
import pefile

source = (root / 'src/native/NativeWeaponPublish.hpp').read_text(encoding='utf-8')
exe = Path('private/game/PBZ.exe')
with exe.open('rb') as stream:
    actual_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
host_array = re.search(r'expected_host\{([^}]+)\}', source).group(1)
expected_hash = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-fA-F]+)', host_array)).hex()
assert actual_hash == expected_hash
pe = pefile.PE(str(exe), fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
rvas = {name: int(value, 16) for name, value in re.findall(r'weapon_cache_(\w+)_rva=0x([0-9a-fA-F]+)', source)}
proof = []
for label in ('getter', 'lookup', 'callback'):
    values = re.search(label+r'_prefix\[\]\{([^}]+)\}', source).group(1)
    expected = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-fA-F]+)', values))
    rva = rvas[label]
    assert len(expected) == 32 and pe.get_data(rva, 32) == expected
    assert any(section.IMAGE_SCN_MEM_EXECUTE and section.VirtualAddress <= rva < section.VirtualAddress+section.Misc_VirtualSize for section in pe.sections)
    proof.append({'entry': label, 'rva': hex(rva), 'verified_prefix': expected.hex()})
loader, = struct.unpack('<Q', pe.get_data(rvas['vtable'], 8))
assert loader == base+rvas['loader']
callback = pe.get_data(rvas['callback'], 0x76)
assert b'\x49\x8d\x40\x08' in callback  # exact ItemId address row+8
assert b'\x48\x8b\x09' in callback       # capture context contains wrapper*
report = {'status': 'passed_offline', 'exe_sha256': actual_hash, 'native_entries': proof,
          'cache_wrapper_rva': '0xe097b80', 'cache_vtable_rva': hex(rvas['vtable']),
          'cache_loader_rva': hex(rvas['loader']), 'callback_item_id_offset': 8,
          'game_or_dll_executed': False, 'game_or_save_modified': False}
(root/'reports/native-publish-gates.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print('PASS native publish: exact executable hash, 3 real executable entry prefixes, vtable target and callback key/context ABI.')

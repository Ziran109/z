#!/usr/bin/env python3
"""测试使用 PCM GUID 创建 AmbiX 文件"""

import sys
import struct
sys.path.insert(0, 'proj_main/ambisonics_wav_fixer')
from ambisonics_wav_fixer import (
    read_all_chunks, find_chunk, parse_fmt_chunk, 
    WAVE_FORMAT_EXTENSIBLE, CHANNEL_MASK_DIRECTOUT
)

# Standard PCM GUID for AmbiX
PCM_GUID_BYTES = bytes([
    0x01, 0x00, 0x00, 0x00,
    0x00, 0x00,
    0x10, 0x00,
    0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71
])

input_file = 'ext_files/ambisonics_channelMask_fixer/260324_008.WAV'
output_file = 'ext_files/ambisonics_channelMask_fixer/output_test/260324_008_ambix_test.WAV'

print(f'Processing: {input_file}')

with open(input_file, 'rb') as f:
    # Read RIFF header
    riff = f.read(4)
    file_size = struct.unpack('<I', f.read(4))[0]
    wave = f.read(4)
    
    # Read all chunks
    chunks = read_all_chunks(f)
    
    # Find fmt chunk
    fmt_chunk = find_chunk(chunks, b'fmt ')
    fmt_info = parse_fmt_chunk(fmt_chunk)
    
    print(f'Original format: channels={fmt_info["channels"]}, rate={fmt_info["sample_rate"]}')
    
    # Create new Extensible fmt data with PCM GUID
    new_fmt_data = bytearray(40)
    struct.pack_into('<H', new_fmt_data, 0, WAVE_FORMAT_EXTENSIBLE)
    struct.pack_into('<H', new_fmt_data, 2, fmt_info['channels'])
    struct.pack_into('<I', new_fmt_data, 4, fmt_info['sample_rate'])
    struct.pack_into('<I', new_fmt_data, 8, fmt_info['byte_rate'])
    struct.pack_into('<H', new_fmt_data, 12, fmt_info['block_align'])
    struct.pack_into('<H', new_fmt_data, 14, fmt_info['bits_per_sample'])
    struct.pack_into('<H', new_fmt_data, 16, 22)  # Extra size
    struct.pack_into('<H', new_fmt_data, 18, fmt_info['bits_per_sample'])
    struct.pack_into('<I', new_fmt_data, 20, CHANNEL_MASK_DIRECTOUT)
    new_fmt_data[24:40] = PCM_GUID_BYTES
    
    # Find data chunk
    data_chunk = find_chunk(chunks, b'data')
    
    # Calculate new file size
    other_chunks_size = sum(8 + c['size'] + (c['size'] % 2) for c in chunks if c['id'] not in [b'fmt ', b'data'])
    new_file_size = 4 + (8 + 40) + other_chunks_size + (8 + data_chunk['size'])
    
    # Write output file
    with open(output_file, 'wb') as out:
        out.write(riff)
        out.write(struct.pack('<I', new_file_size))
        out.write(wave)
        
        # Write fmt chunk
        out.write(b'fmt ')
        out.write(struct.pack('<I', 40))
        out.write(bytes(new_fmt_data))
        
        # Write other chunks
        for chunk in chunks:
            if chunk['id'] not in [b'fmt ', b'data']:
                out.write(chunk['id'])
                out.write(struct.pack('<I', chunk['size']))
                out.write(chunk['data'])
                if chunk['size'] % 2 != 0:
                    out.write(b'\x00')
        
        # Write data chunk
        out.write(b'data')
        out.write(struct.pack('<I', data_chunk['size']))
        out.write(data_chunk['data'])

print(f'Created: {output_file}')

# Verify
with open(output_file, 'rb') as f:
    f.seek(12)
    out_chunks = read_all_chunks(f)
    out_fmt = find_chunk(out_chunks, b'fmt ')
    out_info = parse_fmt_chunk(out_fmt)
    print(f'Output: format=0x{out_info["format_tag"]:04X}, mask=0x{out_info["channel_mask"]:08X}')
    print(f'GUID: {out_info["subformat"].hex()}')
    if out_info['subformat'] == PCM_GUID_BYTES:
        print('GUID check: OK (PCM GUID)')
    else:
        print('GUID check: FAILED')
    
    ixml = find_chunk(out_chunks, b'iXML')
    if ixml:
        print(f'iXML: preserved (size: {ixml["size"]})')
    else:
        print('iXML: NOT found')
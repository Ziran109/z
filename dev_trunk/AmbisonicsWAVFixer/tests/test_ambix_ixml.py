#!/usr/bin/env python3
"""测试修改iXML添加Ambisonics标识"""

import sys
import struct
import re
sys.path.insert(0, 'proj_main/ambisonics_wav_fixer')
from ambisonics_wav_fixer import (
    read_all_chunks, find_chunk, parse_fmt_chunk, 
    WAVE_FORMAT_EXTENSIBLE, CHANNEL_MASK_DIRECTOUT,
    AMBISONIC_B_FORMAT_GUID_BYTES
)

input_file = 'ext_files/ambisonics_channelMask_fixer/260324_008.WAV'
output_file = 'ext_files/ambisonics_channelMask_fixer/output_test/260324_008_ambix_ixml_test.WAV'

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
    
    # Create new Extensible fmt data with AMBISONIC_B_FORMAT GUID
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
    new_fmt_data[24:40] = AMBISONIC_B_FORMAT_GUID_BYTES
    
    # Find and modify iXML chunk
    ixml_chunk = find_chunk(chunks, b'iXML')
    if ixml_chunk:
        ixml_data = ixml_chunk['data']
        # Find valid UTF-8 content
        valid_end = 0
        for i in range(len(ixml_data)):
            try:
                ixml_data[:i+1].decode('utf-8')
                valid_end = i + 1
            except:
                break
        ixml_content = ixml_data[:valid_end].decode('utf-8')
        
        # Add AMBISONICS tag with ACN/SN3D specification
        # According to iXML spec, we can add:
        # <AMBISONICS><ORDER>1</ORDER><NORMALIZATION>SN3D</NORMALIZATION><CHANNEL_ORDERING>ACN</CHANNEL_ORDERING></AMBISONICS>
        
        # Find the position to insert (after TRACK_LIST or before closing BWFXML)
        insert_pos = ixml_content.find('</BWFXML>')
        if insert_pos > 0:
            ambisonics_tag = '''\t<AMBISONICS>
\t\t<ORDER>1</ORDER>
\t\t<NORMALIZATION>SN3D</NORMALIZATION>
\t\t<CHANNEL_ORDERING>ACN</CHANNEL_ORDERING>
\t</AMBISONICS>
'''
            new_ixml_content = ixml_content[:insert_pos] + ambisonics_tag + ixml_content[insert_pos:]
            new_ixml_data = new_ixml_content.encode('utf-8')
            # Pad to original size or larger
            if len(new_ixml_data) < len(ixml_data):
                new_ixml_data = new_ixml_data + b'\xff' * (len(ixml_data) - len(new_ixml_data))
            print(f'iXML modified: added AMBISONICS tag with ACN/SN3D')
            print(f'New iXML size: {len(new_ixml_data)} (original: {len(ixml_data)})')
        else:
            new_ixml_data = ixml_data
            print('Could not find insertion point in iXML')
    else:
        new_ixml_data = None
        print('No iXML chunk found')
    
    # Find data chunk
    data_chunk = find_chunk(chunks, b'data')
    
    # Calculate new file size
    new_ixml_size = len(new_ixml_data) if new_ixml_data else ixml_chunk['size']
    other_chunks_size = sum(8 + c['size'] + (c['size'] % 2) for c in chunks if c['id'] not in [b'fmt ', b'data', b'iXML'])
    new_file_size = 4 + (8 + 40) + other_chunks_size + (8 + new_ixml_size) + (8 + data_chunk['size'])
    
    # Write output file
    with open(output_file, 'wb') as out:
        out.write(riff)
        out.write(struct.pack('<I', new_file_size))
        out.write(wave)
        
        # Write fmt chunk
        out.write(b'fmt ')
        out.write(struct.pack('<I', 40))
        out.write(bytes(new_fmt_data))
        
        # Write other chunks (except fmt, data, iXML)
        for chunk in chunks:
            if chunk['id'] not in [b'fmt ', b'data', b'iXML']:
                out.write(chunk['id'])
                out.write(struct.pack('<I', chunk['size']))
                out.write(chunk['data'])
                if chunk['size'] % 2 != 0:
                    out.write(b'\x00')
        
        # Write modified iXML chunk
        if new_ixml_data:
            out.write(b'iXML')
            out.write(struct.pack('<I', len(new_ixml_data)))
            out.write(new_ixml_data)
            if len(new_ixml_data) % 2 != 0:
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
    print(f'\nOutput verification:')
    print(f'Format: 0x{out_info["format_tag"]:04X}')
    print(f'Channel Mask: 0x{out_info["channel_mask"]:08X}')
    print(f'GUID: {out_info["subformat"].hex()}')
    
    # Check iXML
    out_ixml = find_chunk(out_chunks, b'iXML')
    if out_ixml:
        ixml_data = out_ixml['data']
        valid_end = 0
        for i in range(len(ixml_data)):
            try:
                ixml_data[:i+1].decode('utf-8')
                valid_end = i + 1
            except:
                break
        ixml_content = ixml_data[:valid_end].decode('utf-8')
        print(f'iXML size: {out_ixml["size"]}')
        
        # Check for AMBISONICS tag
        if '<AMBISONICS>' in ixml_content:
            print('AMBISONICS tag: FOUND')
            # Extract and print the tag content
            start = ixml_content.find('<AMBISONICS>')
            end = ixml_content.find('</AMBISONICS>') + len('</AMBISONICS>')
            print(f'Content: {ixml_content[start:end]}')
        else:
            print('AMBISONICS tag: NOT FOUND')
        
        # Check channel ordering
        if 'ACN' in ixml_content:
            print('Channel ordering: ACN')
        if 'SN3D' in ixml_content:
            print('Normalization: SN3D')
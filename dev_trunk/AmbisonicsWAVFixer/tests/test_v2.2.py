#!/usr/bin/env python3
"""Test script for ambisonics_wav_fixer v2.2"""

import sys
sys.path.insert(0, 'proj_main/ambisonics_wav_fixer')
from ambisonics_wav_fixer import process_wav_file, read_all_chunks, find_chunk, parse_fmt_chunk
import os

def test_file(input_file, output_file, channel_order='ACN'):
    """Test processing a single file."""
    print(f'\n=== Testing {os.path.basename(input_file)} ({channel_order}) ===')
    
    if not os.path.exists(input_file):
        print(f'ERROR: Input file not found: {input_file}')
        return
    
    # Process file
    status, msg = process_wav_file(input_file, output_file, False, None, channel_order)
    print(f'Result: {status} - {msg}')
    
    if status != 'SUCCESS':
        return
    
    # Verify output
    print('\nVerifying output file...')
    with open(output_file, 'rb') as f:
        if f.read(4) != b'RIFF':
            print('ERROR: Not RIFF')
            return
        f.read(4)  # file size
        if f.read(4) != b'WAVE':
            print('ERROR: Not WAVE')
            return
        
        chunks = read_all_chunks(f)
        
        # Check fmt chunk
        fmt_chunk = find_chunk(chunks, b'fmt ')
        if fmt_chunk:
            fmt_info = parse_fmt_chunk(fmt_chunk)
            print(f'Format: 0x{fmt_info["format_tag"]:04X}')
            print(f'Channels: {fmt_info["channels"]}')
            print(f'Sample Rate: {fmt_info["sample_rate"]}')
            print(f'Channel Mask: 0x{fmt_info["channel_mask"]:08X}')
        
        # Check for iXML
        ixml = find_chunk(chunks, b'iXML')
        if ixml:
            print('\niXML chunk found!')
            ixml_text = ixml['data'].decode('utf-8', errors='ignore')
            # Find track names
            import re
            tracks = re.findall(r'<TRACK_NAME>([^<]+)</TRACK_NAME>', ixml_text)
            print(f'Track names: {tracks}')
        else:
            print('\nERROR: No iXML chunk found!')
        
        # Check for bext
        bext = find_chunk(chunks, b'bext')
        if bext:
            print('\nbext chunk found!')
        else:
            print('\nERROR: No bext chunk found!')

# Test files
output_dir = 'ext_files/ambisonics_channelMask_fixer/output_test'
os.makedirs(output_dir, exist_ok=True)

# Test Pro Tools file (Extensible format)
test_file(
    'ext_files/ambisonics_channelMask_fixer/TEST_protools.wav',
    os.path.join(output_dir, 'TEST_protools_fixed.wav'),
    'ACN'
)

# Test Reaper file (PCM format)
test_file(
    'ext_files/ambisonics_channelMask_fixer/TEST_reaper.wav',
    os.path.join(output_dir, 'TEST_reaper_fixed.wav'),
    'ACN'
)

# Test with FuMa channel order
test_file(
    'ext_files/ambisonics_channelMask_fixer/TEST_protools.wav',
    os.path.join(output_dir, 'TEST_protools_fuma.wav'),
    'FuMa'
)

print('\n=== All tests completed ===')
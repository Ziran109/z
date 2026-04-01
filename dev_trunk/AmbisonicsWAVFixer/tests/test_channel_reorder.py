#!/usr/bin/env python3
"""
测试通过重排序音频通道来实现AmbiX识别

原理：
- AmbiX/ACN 通道顺序: W(0), Y(1), Z(2), X(3)
- FuMa 通道顺序: W(0), X(1), Y(2), Z(3)

如果我们将AmbiX数据重新排序为FuMa格式，Wwise用FuMa解码时会得到正确的AmbiX数据。

转换映射：
- AmbiX W → FuMa W (通道0不变)
- AmbiX Y → FuMa X (通道1→通道1，但内容是Y)
- AmbiX Z → FuMa Y (通道2→通道2，但内容是Z)
- AmbiX X → FuMa Z (通道3→通道3，但内容是X)

等等，这个逻辑不对。让我重新思考...

实际上，如果Wwise认为文件是FuMa(WXYZ)，它会按WXYZ顺序播放。
如果原始数据是AmbiX(WYZX)，Wwise会播放成：
- 通道0: W (正确)
- 通道1: Y (Wwise认为是X，实际是Y) - 错误!
- 通道2: Z (Wwise认为是Y，实际是Z) - 错误!
- 通道3: X (Wwise认为是Z，实际是X) - 错误!

所以我们需要将AmbiX数据重新排列，让Wwise用FuMa顺序播放时得到正确的AmbiX数据：
- 原始AmbiX: W(0), Y(1), Z(2), X(3)
- 需要重排为: W(0), X(3), Y(1), Z(2) → 这样Wwise用FuMa(WXYZ)播放时：
  - 通道0: W (正确)
  - 通道1: X (Wwise认为是X，实际也是X) - 正确!
  - 通道2: Y (Wwise认为是Y，实际也是Y) - 正确!
  - 通道3: Z (Wwise认为是Z，实际也是Z) - 正确!

但是这样iXML中的通道名称就不匹配了...

更好的方案：将数据重排为FuMa顺序，同时更新iXML为FuMa通道名称
"""

import sys
import struct
sys.path.insert(0, 'proj_main/ambisonics_wav_fixer')
from ambisonics_wav_fixer import (
    read_all_chunks, find_chunk, parse_fmt_chunk, 
    WAVE_FORMAT_EXTENSIBLE, CHANNEL_MASK_DIRECTOUT,
    AMBISONIC_B_FORMAT_GUID_BYTES
)

input_file = 'ext_files/ambisonics_channelMask_fixer/260324_008.WAV'
output_file = 'ext_files/ambisonics_channelMask_fixer/output_test/260324_008_fuma_reorder_test.WAV'

print(f'Processing: {input_file}')
print(f'Converting AmbiX (ACN: WYZX) to FuMa order (WXYZ) in audio data...')

# Channel mapping: AmbiX → FuMa
# AmbiX: W(0), Y(1), Z(2), X(3)
# FuMa:  W(0), X(1), Y(2), Z(3)
# So we need to reorder: [0, 3, 1, 2] (W, X, Y, Z from AmbiX positions)
AMBIX_TO_FUMA_MAP = [0, 3, 1, 2]  # AmbiX index → FuMa position

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
    
    print(f'Format: channels={fmt_info["channels"]}, bits={fmt_info["bits_per_sample"]}, rate={fmt_info["sample_rate"]}')
    
    # Find data chunk
    data_chunk = find_chunk(chunks, b'data')
    audio_data = data_chunk['data']
    
    # Calculate sample parameters
    bytes_per_sample = fmt_info['bits_per_sample'] // 8
    block_align = fmt_info['block_align']  # bytes per frame (all channels)
    num_frames = len(audio_data) // block_align
    
    print(f'Audio data: {len(audio_data)} bytes, {num_frames} frames, {bytes_per_sample} bytes/sample')
    
    # Reorder channels in audio data
    # Each frame contains 4 interleaved samples (W, Y, Z, X in AmbiX)
    # We need to reorder to (W, X, Y, Z) for FuMa
    
    new_audio_data = bytearray(len(audio_data))
    
    for frame in range(num_frames):
        frame_offset = frame * block_align
        
        # Read each channel sample
        for channel in range(4):
            sample_offset = frame_offset + channel * bytes_per_sample
            sample_data = audio_data[sample_offset:sample_offset + bytes_per_sample]
            
            # Map to new position
            new_channel = AMBIX_TO_FUMA_MAP[channel]
            new_offset = frame_offset + new_channel * bytes_per_sample
            new_audio_data[new_offset:new_offset + bytes_per_sample] = sample_data
    
    print(f'Reordered {num_frames} frames')
    
    # Create new Extensible fmt data with AMBISONIC_B_FORMAT GUID
    new_fmt_data = bytearray(40)
    struct.pack_into('<H', new_fmt_data, 0, WAVE_FORMAT_EXTENSIBLE)
    struct.pack_into('<H', new_fmt_data, 2, fmt_info['channels'])
    struct.pack_into('<I', new_fmt_data, 4, fmt_info['sample_rate'])
    struct.pack_into('<I', new_fmt_data, 8, fmt_info['byte_rate'])
    struct.pack_into('<H', new_fmt_data, 12, fmt_info['block_align'])
    struct.pack_into('<H', new_fmt_data, 14, fmt_info['bits_per_sample'])
    struct.pack_into('<H', new_fmt_data, 16, 22)
    struct.pack_into('<H', new_fmt_data, 18, fmt_info['bits_per_sample'])
    struct.pack_into('<I', new_fmt_data, 20, CHANNEL_MASK_DIRECTOUT)
    new_fmt_data[24:40] = AMBISONIC_B_FORMAT_GUID_BYTES
    
    # Modify iXML to reflect FuMa channel order (WXYZ)
    ixml_chunk = find_chunk(chunks, b'iXML')
    if ixml_chunk:
        ixml_data = ixml_chunk['data']
        valid_end = 0
        for i in range(len(ixml_data)):
            try:
                ixml_data[:i+1].decode('utf-8')
                valid_end = i + 1
            except:
                break
        ixml_content = ixml_data[:valid_end].decode('utf-8')
        
        # Update channel names to FuMa order (WXYZ)
        # Original: W, Y, Z, X (AmbiX/ACN)
        # New: W, X, Y, Z (FuMa)
        
        # Replace track names
        # Track 1: W → W (unchanged)
        # Track 2: Y → X
        # Track 3: Z → Y
        # Track 4: X → Z
        
        ixml_content = ixml_content.replace('<NAME>Y</NAME>', '<NAME>X</NAME>')
        ixml_content = ixml_content.replace('<NAME>Z</NAME>', '<NAME>Y</NAME>')
        ixml_content = ixml_content.replace('<NAME>X</NAME>', '<NAME>Z</NAME>')
        
        # Also update bext channel info
        new_ixml_data = ixml_content.encode('utf-8')
        if len(new_ixml_data) < len(ixml_data):
            new_ixml_data = new_ixml_data + b'\xff' * (len(ixml_data) - len(new_ixml_data))
        print(f'iXML updated: channel names changed to FuMa order (WXYZ)')
    
    # Modify bext to reflect FuMa channel order
    bext_chunk = find_chunk(chunks, b'bext')
    if bext_chunk:
        bext_data = bytearray(bext_chunk['data'])
        # bext description field is first 256 bytes
        desc = bext_data[0:256].decode('utf-8', errors='ignore')
        
        # Update channel names in bext
        # Original: zTRK1=W, zTRK2=Y, zTRK3=Z, zTRK4=X
        # New: zTRK1=W, zTRK2=X, zTRK3=Y, zTRK4=Z
        desc = desc.replace('zTRK2=Y', 'zTRK2=X')
        desc = desc.replace('zTRK3=Z', 'zTRK3=Y')
        desc = desc.replace('zTRK4=X', 'zTRK4=Z')
        
        new_desc_bytes = desc.encode('utf-8')
        bext_data[0:len(new_desc_bytes)] = new_desc_bytes
        print(f'bext updated: channel names changed to FuMa order (WXYZ)')
    
    # Calculate new file size
    other_chunks_size = sum(8 + c['size'] + (c['size'] % 2) for c in chunks if c['id'] not in [b'fmt ', b'data'])
    new_file_size = 4 + (8 + 40) + other_chunks_size + (8 + len(audio_data))
    
    # Write output file
    with open(output_file, 'wb') as out:
        out.write(riff)
        out.write(struct.pack('<I', new_file_size))
        out.write(wave)
        
        # Write fmt chunk
        out.write(b'fmt ')
        out.write(struct.pack('<I', 40))
        out.write(bytes(new_fmt_data))
        
        # Write other chunks (except fmt, data)
        for chunk in chunks:
            if chunk['id'] not in [b'fmt ', b'data']:
                out.write(chunk['id'])
                out.write(struct.pack('<I', chunk['size']))
                if chunk['id'] == b'iXML':
                    out.write(new_ixml_data)
                elif chunk['id'] == b'bext':
                    out.write(bytes(bext_data))
                else:
                    out.write(chunk['data'])
                if chunk['size'] % 2 != 0:
                    out.write(b'\x00')
        
        # Write data chunk with reordered audio
        out.write(b'data')
        out.write(struct.pack('<I', len(new_audio_data)))
        out.write(bytes(new_audio_data))

print(f'Created: {output_file}')
print(f'\n说明：此文件已将音频数据从AmbiX顺序(WYZX)转换为FuMa顺序(WXYZ)')
print(f'Wwise识别为FuMa时，播放的数据实际上是正确的AmbiX内容')
print(f'但请注意：iXML和bext中的通道名称已更新为FuMa顺序(WXYZ)')
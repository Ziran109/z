import struct
import os

def analyze_wav_full(filepath):
    """完整分析 WAV 文件结构"""
    print(f'\n{'='*60}')
    print(f'分析文件: {os.path.basename(filepath)}')
    print(f'{'='*60}')
    
    with open(filepath, 'rb') as f:
        # RIFF header
        riff = f.read(4)
        print(f'RIFF Header: {riff}')
        file_size = struct.unpack('<I', f.read(4))[0]
        print(f'File Size: {file_size} bytes')
        wave = f.read(4)
        print(f'WAVE Format: {wave}')
        
        # Read all chunks
        chunks = []
        while f.tell() < file_size + 8:
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break
            chunk_size = struct.unpack('<I', f.read(4))[0]
            chunk_data = f.read(chunk_size)
            
            chunks.append({
                'id': chunk_id,
                'size': chunk_size,
                'data': chunk_data
            })
            
            # Handle padding byte
            if chunk_size % 2 == 1:
                f.read(1)
        
        # Analyze each chunk
        for chunk in chunks:
            chunk_id = chunk['id']
            chunk_size = chunk['size']
            chunk_data = chunk['data']
            
            print(f'\n--- Chunk: {chunk_id} (size: {chunk_size}) ---')
            
            if chunk_id == b'fmt ':
                # Format chunk
                format_tag = struct.unpack('<H', chunk_data[0:2])[0]
                channels = struct.unpack('<H', chunk_data[2:4])[0]
                sample_rate = struct.unpack('<I', chunk_data[4:8])[0]
                byte_rate = struct.unpack('<I', chunk_data[8:12])[0]
                block_align = struct.unpack('<H', chunk_data[12:14])[0]
                bits_per_sample = struct.unpack('<H', chunk_data[14:16])[0]
                
                format_name = "PCM" if format_tag == 1 else "Extensible" if format_tag == 0xFFFE else f"Unknown(0x{format_tag:04X})"
                print(f'  Format Tag: 0x{format_tag:04X} ({format_name})')
                print(f'  Channels: {channels}')
                print(f'  Sample Rate: {sample_rate} Hz')
                print(f'  Byte Rate: {byte_rate}')
                print(f'  Block Align: {block_align}')
                print(f'  Bits Per Sample: {bits_per_sample}')
                
                if chunk_size >= 18:
                    cb_size = struct.unpack('<H', chunk_data[16:18])[0]
                    print(f'  cbSize: {cb_size}')
                
                if chunk_size >= 40 and format_tag == 0xFFFE:
                    # Extensible format
                    valid_bits = struct.unpack('<H', chunk_data[18:20])[0]
                    channel_mask = struct.unpack('<I', chunk_data[20:24])[0]
                    subformat = chunk_data[24:40]
                    
                    print(f'  Valid Bits Per Sample: {valid_bits}')
                    print(f'  Channel Mask: 0x{channel_mask:08X}')
                    print(f'  SubFormat GUID (raw): {subformat.hex()}')
                    
                    # Parse GUID
                    guid_data1 = struct.unpack('<I', subformat[0:4])[0]
                    guid_data2 = struct.unpack('<H', subformat[4:6])[0]
                    guid_data3 = struct.unpack('<H', subformat[6:8])[0]
                    guid_data4 = subformat[8:16]
                    
                    print(f'  SubFormat GUID: {{{guid_data1:08X}-{guid_data2:04X}-{guid_data3:04X}-{guid_data4.hex()}}}')
                    
                    # Check known GUIDs
                    pcm_guid = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71])
                    ambisonics_guid = bytes([0x61, 0x32, 0xE8, 0xE9, 0xA2, 0x8F, 0x3B, 0x4B, 0xA1, 0xD0, 0x5F, 0x9B, 0x49, 0xA8, 0x30, 0xBA])
                    
                    if subformat == pcm_guid:
                        print(f'  SubFormat Type: PCM')
                    elif subformat == ambisonics_guid:
                        print(f'  SubFormat Type: Ambisonics (Windows)')
                    else:
                        print(f'  SubFormat Type: Unknown/Custom')
            
            elif chunk_id == b'data':
                print(f'  Audio Data Size: {chunk_size} bytes')
                print(f'  Audio Duration: {chunk_size / (byte_rate if byte_rate else 1):.2f} seconds (estimated)')
            
            elif chunk_id == b'bext':
                # Broadcast extension chunk
                print(f'  Broadcast Extension Chunk')
                if chunk_size >= 602:
                    description = chunk_data[0:256].rstrip(b'\x00').decode('utf-8', errors='ignore')
                    originator = chunk_data[256:288].rstrip(b'\x00').decode('utf-8', errors='ignore')
                    print(f'  Description: {description}')
                    print(f'  Originator: {originator}')
            
            else:
                # Other chunks - show raw data preview
                preview_len = min(64, len(chunk_data))
                print(f'  Data Preview: {chunk_data[:preview_len].hex()}')

# Analyze all test files
test_dir = 'ext_files/ambisonics_channelMask_fixer'
for filename in os.listdir(test_dir):
    if filename.lower().endswith('.wav'):
        filepath = os.path.join(test_dir, filename)
        analyze_wav_full(filepath)
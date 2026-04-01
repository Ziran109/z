import struct
import os

def read_full_ixml(filepath):
    """读取完整的 iXML chunk"""
    print(f'\n分析文件: {os.path.basename(filepath)}')
    
    with open(filepath, 'rb') as f:
        # Skip RIFF header (12 bytes)
        f.read(12)
        
        while True:
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break
            chunk_size = struct.unpack('<I', f.read(4))[0]
            
            if chunk_id == b'iXML':
                chunk_data = f.read(chunk_size)
                
                # Find valid UTF-8 portion (stop at first invalid byte)
                valid_end = 0
                for i in range(len(chunk_data)):
                    try:
                        chunk_data[:i+1].decode('utf-8')
                        valid_end = i + 1
                    except:
                        break
                
                xml_content = chunk_data[:valid_end].decode('utf-8')
                print(f'\n--- iXML Content (前 {valid_end} 字节) ---')
                print(xml_content)
                
                # Also show remaining bytes as hex
                if valid_end < len(chunk_data):
                    print(f'\n--- 剩余数据 (hex) ---')
                    print(chunk_data[valid_end:valid_end+100].hex())
                break
            else:
                skip = chunk_size
                if chunk_size % 2 == 1:
                    skip += 1
                f.seek(skip, 1)

# Analyze Zoom H3 VR file
read_full_ixml('ext_files/ambisonics_channelMask_fixer/260324_008.WAV')
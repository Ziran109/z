#!/usr/bin/env python3
"""测试修复后的脚本"""

import os
import sys
import shutil

# 导入处理函数
sys.path.insert(0, 'proj_main/ambisonics_wav_fixer')
from ambisonics_wav_fixer import process_wav_file, read_all_chunks, find_chunk, parse_fmt_chunk, AMBISONICS_GUID_BYTES, CHANNEL_MASK_DIRECTOUT

import struct

def analyze_wav_full(filepath):
    """完整分析 WAV 文件"""
    print(f'\n{"="*60}')
    print(f'文件: {os.path.basename(filepath)}')
    print(f'{"="*60}')
    
    with open(filepath, 'rb') as f:
        # RIFF header
        riff = f.read(4)
        file_size = struct.unpack('<I', f.read(4))[0]
        wave = f.read(4)
        print(f'RIFF: {riff}, Size: {file_size}')
        
        # 读取所有 chunks
        chunks = read_all_chunks(f)
        
        print(f'\nChunks 列表:')
        for chunk in chunks:
            print(f'  {chunk["id"]} (size: {chunk["size"]})')
        
        # 分析 fmt chunk
        fmt_chunk = find_chunk(chunks, b'fmt ')
        if fmt_chunk:
            fmt_info = parse_fmt_chunk(fmt_chunk)
            print(f'\nfmt 分析:')
            print(f'  Format Tag: 0x{fmt_info["format_tag"]:04X}')
            print(f'  Channels: {fmt_info["channels"]}')
            print(f'  Sample Rate: {fmt_info["sample_rate"]}')
            if fmt_info['channel_mask'] is not None:
                print(f'  Channel Mask: 0x{fmt_info["channel_mask"]:08X}')
            if fmt_info['subformat'] is not None:
                is_ambisonics = fmt_info['subformat'] == AMBISONICS_GUID_BYTES
                print(f'  SubFormat: {"Ambisonics" if is_ambisonics else "Other"}')
        
        # 检查 iXML
        ixml_chunk = find_chunk(chunks, b'iXML')
        if ixml_chunk:
            print(f'\niXML chunk: 存在 ✓ (size: {ixml_chunk["size"]})')
            # 显示部分内容
            try:
                data = ixml_chunk['data']
                valid_end = 0
                for i in range(len(data)):
                    try:
                        data[:i+1].decode('utf-8')
                        valid_end = i + 1
                    except:
                        break
                preview = data[:min(valid_end, 300)].decode('utf-8')
                # 查找 TRACK_LIST
                if '<TRACK_LIST>' in preview:
                    print('  包含 TRACK_LIST ✓')
            except:
                pass
        else:
            print(f'\niXML chunk: 不存在 ✗')
        
        # 检查 bext
        bext_chunk = find_chunk(chunks, b'bext')
        if bext_chunk:
            print(f'\nbext chunk: 存在 ✓ (size: {bext_chunk["size"]})')
            try:
                desc = bext_chunk['data'][0:256].rstrip(b'\x00').decode('utf-8', errors='ignore')
                if 'zTRK' in desc:
                    print('  包含 zTRK 通道信息 ✓')
            except:
                pass
        else:
            print(f'\nbext chunk: 不存在 ✗')

# 测试目录
input_dir = 'ext_files/ambisonics_channelMask_fixer'
output_dir = 'ext_files/ambisonics_channelMask_fixer/output_test'

# 创建输出目录
if os.path.exists(output_dir):
    shutil.rmtree(output_dir)
os.makedirs(output_dir)

# 分析原始文件
print('\n' + '='*60)
print('原始 Zoom H3 VR 文件分析')
print('='*60)
analyze_wav_full(os.path.join(input_dir, '260324_008.WAV'))

# 处理文件
print('\n' + '='*60)
print('处理文件...')
print('='*60)

input_file = os.path.join(input_dir, '260324_008.WAV')
output_file = os.path.join(output_dir, '260324_008.WAV')

status, message = process_wav_file(input_file, output_file, in_place=False)
print(f'处理结果: {status} - {message}')

# 分析处理后的文件
print('\n' + '='*60)
print('处理后文件分析')
print('='*60)
analyze_wav_full(output_file)

print('\n' + '='*60)
print('测试完成')
print('='*60)
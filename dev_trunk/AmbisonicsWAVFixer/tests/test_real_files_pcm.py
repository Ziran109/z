#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本 - 使用 TEST_protools.wav 和 TEST_reaper.wav 测试 PCM 格式转换功能
重点验证：
1. Extensible 格式转换为 PCM 格式
2. PCM 格式保持不变
3. 音频数据完全相同
"""

import os
import sys
import struct
import hashlib
from pathlib import Path

# 添加项目路径
project_path = Path(__file__).parent.parent / 'proj_main' / 'AmbisonicsWAVFixer'
sys.path.insert(0, str(project_path))

# 导入处理函数
import importlib.util
spec = importlib.util.spec_from_file_location("AmbisonicsWAVFixer", str(project_path / "AmbisonicsWAVFixer.py"))
ambisonics_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ambisonics_module)

# 从模块获取常量和函数
WAVE_FORMAT_PCM = ambisonics_module.WAVE_FORMAT_PCM
WAVE_FORMAT_EXTENSIBLE = ambisonics_module.WAVE_FORMAT_EXTENSIBLE
process_wav_file = ambisonics_module.process_wav_file
read_all_chunks = ambisonics_module.read_all_chunks
find_chunk = ambisonics_module.find_chunk
parse_fmt_chunk = ambisonics_module.parse_fmt_chunk


def get_file_hash(file_path):
    """计算文件的 MD5 哈希值"""
    hash_md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_audio_data_hash(file_path):
    """仅计算音频数据部分的哈希值"""
    with open(file_path, 'rb') as f:
        # 验证 RIFF/WAVE
        riff = f.read(4)
        if riff != b'RIFF':
            return None
        
        file_size = struct.unpack('<I', f.read(4))[0]
        wave = f.read(4)
        if wave != b'WAVE':
            return None
        
        # 读取所有 chunks
        chunks = read_all_chunks(f)
        
        # 查找 data chunk
        data_chunk = find_chunk(chunks, b'data')
        if data_chunk is None:
            return None
        
        # 计算音频数据的哈希
        hash_md5 = hashlib.md5()
        hash_md5.update(data_chunk['data'])
        return hash_md5.hexdigest()


def verify_wav_format(file_path):
    """
    详细验证 WAV 文件格式信息
    
    返回:
        dict: 包含详细的格式信息
    """
    with open(file_path, 'rb') as f:
        # 验证 RIFF/WAVE
        riff = f.read(4)
        if riff != b'RIFF':
            return {'error': "不是 RIFF 文件"}
        
        file_size = struct.unpack('<I', f.read(4))[0]
        wave = f.read(4)
        if wave != b'WAVE':
            return {'error': "不是 WAVE 文件"}
        
        # 读取所有 chunks
        chunks = read_all_chunks(f)
        
        # 查找 fmt chunk
        fmt_chunk = find_chunk(chunks, b'fmt ')
        if fmt_chunk is None:
            return {'error': "找不到 fmt chunk"}
        
        # 解析 fmt chunk
        fmt_info = parse_fmt_chunk(fmt_chunk)
        if fmt_info is None:
            return {'error': "无法解析 fmt chunk"}
        
        # 查找 data chunk
        data_chunk = find_chunk(chunks, b'data')
        audio_size = len(data_chunk['data']) if data_chunk else 0
        
        # 检查其他 chunks
        chunk_list = []
        for chunk in chunks:
            chunk_list.append({
                'id': chunk['id'].decode('ascii', errors='replace'),
                'size': chunk['size']
            })
        
        return {
            'format_tag': fmt_info['format_tag'],
            'format_name': 'PCM' if fmt_info['format_tag'] == WAVE_FORMAT_PCM else 
                          'Extensible' if fmt_info['format_tag'] == WAVE_FORMAT_EXTENSIBLE else 
                          f'Unknown (0x{fmt_info["format_tag"]:04X})',
            'channels': fmt_info['channels'],
            'sample_rate': fmt_info['sample_rate'],
            'bits_per_sample': fmt_info['bits_per_sample'],
            'byte_rate': fmt_info['byte_rate'],
            'block_align': fmt_info['block_align'],
            'fmt_chunk_size': fmt_chunk['size'],
            'audio_data_size': audio_size,
            'chunks': chunk_list,
            'has_ixml': find_chunk(chunks, b'iXML') is not None,
            'has_bext': find_chunk(chunks, b'bext') is not None,
            'file_size': file_size + 8,  # RIFF header 不包含在 file_size 字段中
        }


def compare_audio_data(file1, file2):
    """
    比较两个文件的音频数据是否完全相同
    
    返回:
        tuple: (是否相同, 差异描述)
    """
    with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
        # 验证 RIFF/WAVE
        for f, name in [(f1, 'file1'), (f2, 'file2')]:
            if f.read(4) != b'RIFF':
                return False, f"{name}: 不是 RIFF 文件"
            f.read(4)
            if f.read(4) != b'WAVE':
                return False, f"{name}: 不是 WAVE 文件"
        
        # 读取所有 chunks
        chunks1 = read_all_chunks(f1)
        chunks2 = read_all_chunks(f2)
        
        # 查找 data chunks
        data1 = find_chunk(chunks1, b'data')
        data2 = find_chunk(chunks2, b'data')
        
        if data1 is None:
            return False, "file1: 找不到 data chunk"
        if data2 is None:
            return False, "file2: 找不到 data chunk"
        
        # 比较音频数据
        if data1['size'] != data2['size']:
            return False, f"音频数据大小不同: {data1['size']} vs {data2['size']}"
        
        if data1['data'] != data2['data']:
            # 找出第一个不同的字节
            for i in range(len(data1['data'])):
                if data1['data'][i] != data2['data'][i]:
                    return False, f"音频数据在第 {i} 字节处不同"
            return False, "音频数据不同"
        
        return True, "音频数据完全相同"


def test_file(input_file, test_name):
    """
    测试单个文件的 PCM 格式保留
    
    参数:
        input_file: 输入文件路径
        test_name: 测试名称
    
    返回:
        bool: 测试是否通过
    """
    print(f"\n{'=' * 70}")
    print(f"测试: {test_name}")
    print(f"文件: {input_file}")
    print('=' * 70)
    
    # 检查文件是否存在
    if not os.path.exists(input_file):
        print(f"✗ 错误: 文件不存在 - {input_file}")
        return False
    
    # 创建输出目录
    output_dir = Path(__file__).parent.parent / 'ext_files' / 'ambisonics_channelMask_fixer' / 'output_test'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 输出文件路径
    output_file = output_dir / f"{Path(input_file).stem}_pcm_test.wav"
    
    # 删除旧输出文件
    if output_file.exists():
        output_file.unlink()
    
    # 验证输入文件格式
    print("\n[输入文件信息]")
    input_info = verify_wav_format(str(input_file))
    if 'error' in input_info:
        print(f"✗ 错误: {input_info['error']}")
        return False
    
    print(f"  格式: {input_info['format_name']} (0x{input_info['format_tag']:04X})")
    print(f"  fmt chunk 大小: {input_info['fmt_chunk_size']} 字节")
    print(f"  通道数: {input_info['channels']}")
    print(f"  采样率: {input_info['sample_rate']} Hz")
    print(f"  位深度: {input_info['bits_per_sample']} bits")
    print(f"  音频数据大小: {input_info['audio_data_size']} 字节")
    print(f"  iXML chunk: {'有' if input_info['has_ixml'] else '无'}")
    print(f"  bext chunk: {'有' if input_info['has_bext'] else '无'}")
    print(f"  文件大小: {input_info['file_size']} 字节")
    print(f"  所有 chunks:")
    for chunk in input_info['chunks']:
        print(f"    - {chunk['id']}: {chunk['size']} 字节")
    
    # 计算输入文件的音频数据哈希
    input_audio_hash = get_audio_data_hash(str(input_file))
    print(f"  音频数据 MD5: {input_audio_hash[:16]}...")
    
    # 处理文件
    print(f"\n[处理文件...]")
    status, message = process_wav_file(str(input_file), str(output_file), 
                                       in_place=False, log_callback=print,
                                       channel_order='AmbiX')
    print(f"处理结果: {status} - {message}")
    
    if status == 'ERROR':
        print(f"✗ 处理失败")
        return False
    
    if status == 'SKIPPED':
        print(f"⚠ 文件被跳过")
        return True
    
    # 验证输出文件格式
    print(f"\n[输出文件信息]")
    output_info = verify_wav_format(str(output_file))
    if 'error' in output_info:
        print(f"✗ 错误: {output_info['error']}")
        return False
    
    print(f"  格式: {output_info['format_name']} (0x{output_info['format_tag']:04X})")
    print(f"  fmt chunk 大小: {output_info['fmt_chunk_size']} 字节")
    print(f"  通道数: {output_info['channels']}")
    print(f"  采样率: {output_info['sample_rate']} Hz")
    print(f"  位深度: {output_info['bits_per_sample']} bits")
    print(f"  音频数据大小: {output_info['audio_data_size']} 字节")
    print(f"  iXML chunk: {'有' if output_info['has_ixml'] else '无'}")
    print(f"  bext chunk: {'有' if output_info['has_bext'] else '无'}")
    print(f"  文件大小: {output_info['file_size']} 字节")
    print(f"  所有 chunks:")
    for chunk in output_info['chunks']:
        print(f"    - {chunk['id']}: {chunk['size']} 字节")
    
    # 计算输出文件的音频数据哈希
    output_audio_hash = get_audio_data_hash(str(output_file))
    print(f"  音频数据 MD5: {output_audio_hash[:16]}...")
    
    # 验证结果
    print(f"\n[验证结果]")
    all_passed = True
    
    # 1. 检查格式是否保留
    if input_info['format_tag'] == WAVE_FORMAT_PCM:
        if output_info['format_tag'] == WAVE_FORMAT_PCM:
            print(f"✓ PCM 格式已正确保留 (0x0001)")
            if output_info['fmt_chunk_size'] == 16:
                print(f"✓ fmt chunk 大小保持 16 字节 (PCM 标准)")
            else:
                print(f"✗ fmt chunk 大小异常: {output_info['fmt_chunk_size']} 字节 (应为 16)")
                all_passed = False
        else:
            print(f"✗ PCM 格式被转换为 {output_info['format_name']}!")
            print(f"  输入格式: 0x{input_info['format_tag']:04X}")
            print(f"  输出格式: 0x{output_info['format_tag']:04X}")
            all_passed = False
    elif input_info['format_tag'] == WAVE_FORMAT_EXTENSIBLE:
        if output_info['format_tag'] == WAVE_FORMAT_EXTENSIBLE:
            print(f"✓ Extensible 格式已正确保留 (0xFFFE)")
        else:
            print(f"⚠ Extensible 格式被转换为 {output_info['format_name']}")
    
    # 2. 检查音频参数是否一致
    if input_info['channels'] == output_info['channels']:
        print(f"✓ 通道数一致: {output_info['channels']}")
    else:
        print(f"✗ 通道数不一致: {input_info['channels']} → {output_info['channels']}")
        all_passed = False
    
    if input_info['sample_rate'] == output_info['sample_rate']:
        print(f"✓ 采样率一致: {output_info['sample_rate']} Hz")
    else:
        print(f"✗ 采样率不一致: {input_info['sample_rate']} → {output_info['sample_rate']}")
        all_passed = False
    
    if input_info['bits_per_sample'] == output_info['bits_per_sample']:
        print(f"✓ 位深度一致: {output_info['bits_per_sample']} bits")
    else:
        print(f"✗ 位深度不一致: {input_info['bits_per_sample']} → {output_info['bits_per_sample']}")
        all_passed = False
    
    # 3. 检查音频数据是否完全相同
    audio_match, audio_msg = compare_audio_data(str(input_file), str(output_file))
    if audio_match:
        print(f"✓ 音频数据完全相同 (PCM 数据未被修改)")
    else:
        print(f"✗ 音频数据被修改: {audio_msg}")
        all_passed = False
    
    # 4. 检查音频数据哈希
    if input_audio_hash == output_audio_hash:
        print(f"✓ 音频数据哈希一致")
    else:
        print(f"✗ 音频数据哈希不一致")
        print(f"  输入: {input_audio_hash}")
        print(f"  输出: {output_audio_hash}")
        all_passed = False
    
    # 5. 检查元数据是否添加
    if output_info['has_ixml']:
        print(f"✓ iXML chunk 已添加")
    else:
        print(f"⚠ iXML chunk 未添加")
    
    if output_info['has_bext']:
        print(f"✓ bext chunk 已添加")
    else:
        print(f"⚠ bext chunk 未添加")
    
    print(f"\n{'=' * 70}")
    if all_passed:
        print(f"✓ 测试通过: {test_name}")
    else:
        print(f"✗ 测试失败: {test_name}")
    print('=' * 70)
    
    return all_passed


def main():
    """主测试函数"""
    print("=" * 70)
    print("AmbisonicsWAVFixer v2.5.1 - PCM 格式保留测试")
    print("使用 TEST_protools.wav 和 TEST_reaper.wav")
    print("=" * 70)
    
    # 测试文件路径
    test_dir = Path(__file__).parent.parent / 'ext_files' / 'ambisonics_channelMask_fixer'
    
    test_files = [
        (test_dir / 'TEST_protools.wav', 'Pro Tools 导出文件'),
        (test_dir / 'TEST_reaper.wav', 'Reaper 导出文件'),
    ]
    
    results = []
    
    for file_path, test_name in test_files:
        result = test_file(str(file_path), test_name)
        results.append((test_name, result))
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    all_passed = True
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {test_name}: {status}")
        if not result:
            all_passed = False
    
    print("=" * 70)
    if all_passed:
        print("✓ 所有测试通过! PCM 格式保留功能正常工作。")
    else:
        print("✗ 部分测试失败! PCM 格式保留功能存在问题。")
    print("=" * 70)
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
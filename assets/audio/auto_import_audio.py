import json
import os
import shutil
import glob

def main():
    downloads_dir = os.path.expanduser('~\\Downloads')
    audio_base_dir = os.path.dirname(os.path.abspath(__file__))
    manifest_path = os.path.join(audio_base_dir, 'audio_manifest.json')

    print(f"Reading manifest from: {manifest_path}")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    # Xây dựng từ điển ánh xạ: Tên bài hát không có đuôi -> Đường dẫn thư mục đích
    file_to_folder = {}
    for category, data in manifest.items():
        if category in ['_comment', '_usage', 'episode_profiles']:
            continue
        
        if category == 'jingles':
            for filename in list(data.keys()):
                if filename.endswith('.mp3') or filename.endswith('.wav'):
                    basename = os.path.splitext(filename)[0]
                    file_to_folder[basename] = os.path.join(audio_base_dir, 'jingles')
        else:
            for subcat, subdata in data.items():
                if subcat.startswith('_'): continue
                for filename in list(subdata.keys()):
                    if filename.endswith('.mp3') or filename.endswith('.wav'):
                        basename = os.path.splitext(filename)[0]
                        file_to_folder[basename] = os.path.join(audio_base_dir, category, subcat)

    # Tìm tất cả file .wav và .mp3 trong Downloads
    wav_files = glob.glob(os.path.join(downloads_dir, '*.wav'))
    mp3_files = glob.glob(os.path.join(downloads_dir, '*.mp3'))
    all_files = wav_files + mp3_files

    if not all_files:
        print("Không tìm thấy file .wav hoặc .mp3 nào trong thư mục Downloads.")
        return

    moved_count = 0
    skipped_count = 0
    manifest_updated = False

    for filepath in all_files:
        filename = os.path.basename(filepath)
        basename, ext = os.path.splitext(filename)
        
        # Xử lý các file bị trình duyệt đổi tên tự động: 'chopping_veg (1).wav' -> 'chopping_veg'
        clean_basename = basename.split(' (')[0].strip()
        
        if clean_basename in file_to_folder:
            target_dir = file_to_folder[clean_basename]
            os.makedirs(target_dir, exist_ok=True)
            
            target_path = os.path.join(target_dir, clean_basename + ext)
            
            # KIỂM TRA BỎ QUA NẾU FILE ĐÃ TỒN TẠI
            if os.path.exists(target_path):
                print(f'⏩ Bỏ qua (Đã tồn tại): {filename}')
                skipped_count += 1
                continue
                
            print(f'✅ Đang chuyển: {filename} -> {target_dir}')
            shutil.move(filepath, target_path)
            moved_count += 1
            
            # Nếu là file .wav, tự động đổi key trong manifest từ .mp3 thành .wav
            if ext.lower() == '.wav':
                for cat, data in manifest.items():
                    if cat in ['_comment', '_usage', 'episode_profiles']: continue
                    if cat == 'jingles':
                        if clean_basename + '.mp3' in manifest[cat]:
                            manifest[cat][clean_basename + '.wav'] = manifest[cat].pop(clean_basename + '.mp3')
                            manifest_updated = True
                    else:
                        for subcat, subdata in data.items():
                            if subcat.startswith('_'): continue
                            if clean_basename + '.mp3' in manifest[cat][subcat]:
                                manifest[cat][subcat][clean_basename + '.wav'] = manifest[cat][subcat].pop(clean_basename + '.mp3')
                                manifest_updated = True

    # Lưu lại file json nếu có file .wav được thay thế
    if manifest_updated:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print("📝 Đã cập nhật lại file audio_manifest.json (chuyển .mp3 thành .wav)")

    print(f'\n🎉 Xong! Đã chuyển {moved_count} file. Bỏ qua {skipped_count} file đã tồn tại.')

if __name__ == "__main__":
    main()

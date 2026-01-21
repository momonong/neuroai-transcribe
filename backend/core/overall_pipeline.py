#!/usr/bin/env python3
"""
完整的 NeuroAI 轉錄流程 (優化版)
包含自動記憶體管理與警告過濾，解決 GPU 卡死問題
"""
import os
import sys
import json
import glob
import gc
import torch
import warnings
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# ==========================================
# 1. 過濾惱人的警告 (Clean Logs)
# ==========================================
# 忽略 Pyannote/Torchaudio 的版本棄用警告
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
# 特別針對 TF32 和 torchaudio backend 的警告
warnings.filterwarnings("ignore", message=".*torchaudio._backend.*")
warnings.filterwarnings("ignore", message=".*TensorFloat-32.*")
warnings.filterwarnings("ignore", message=".*degrees of freedom.*")

# 確保能找到 core 模組
current_dir = Path(__file__).parent
backend_dir = current_dir.parent
sys.path.insert(0, str(backend_dir))

from core.config import config
from core.file_manager import file_manager
from core.split import SmartAudioSplitter
from core.pipeline import PipelinePhase2
from core.stitch import run_stitching_logic
from core.flag import run_anomaly_detector

class OverallPipeline:
    """完整的轉錄流程管理器"""
    
    def __init__(self, video_path: str, case_name: Optional[str] = None, force_reprocess: bool = False):
        """
        初始化完整流程
        """
        self.video_path = Path(video_path)
        self.force_reprocess = force_reprocess
        
        if not self.video_path.exists():
            raise FileNotFoundError(f"找不到影片檔案: {video_path}")
        
        # 決定案例名稱
        if case_name is None:
            # 從檔名自動生成案例名稱
            timestamp = datetime.now().strftime("%Y%m%d-%H%M")
            video_name = self.video_path.stem
            self.case_name = f"{timestamp}-{video_name}"
        else:
            self.case_name = case_name
        
        # 設定案例目錄
        self.case_dir = file_manager.get_case_dir(self.case_name)
        
        # 初始化各個處理器
        self.splitter = SmartAudioSplitter(case_name=self.case_name)
        self.ai_processor = PipelinePhase2()
        
        print(f"🎬 初始化完整流程")
        print(f"   📄 影片檔案:  {self.video_path.name}")
        print(f"   📁 案例名稱: {self.case_name}")
        print(f"   📂 輸出目錄: {self.case_dir}")
        print(f"   🔄 強制重新處理: {'是' if force_reprocess else '否'}")

    def _clean_gpu(self):
        """
        強制清理 GPU 記憶體與同步
        這是解決 Pipeline 卡死的關鍵函數
        """
        gc.collect() # 清除 Python 無用變數
        if torch.cuda.is_available():
            torch.cuda.synchronize() # 等待所有 GPU 任務完成
            torch.cuda.empty_cache() # 釋放顯存
            torch.cuda.synchronize() # 再次確認
        # print("   🧹 VRAM Cleaned & Synced.") 

    def step1_split_audio(self, num_chunks: int = 4) -> List[Dict[str, Any]]:
        """步驟 1: 音訊切分"""
        print(f"\n🔪 [步驟 1/6] 音訊切分...")
        print("=" * 50)
        
        # 檢查是否已有 chunk 檔案
        existing_chunks = list(self.case_dir.glob("chunk_*.wav"))
        
        if existing_chunks and not self.force_reprocess:
            print(f"⏩ 發現 {len(existing_chunks)} 個現有 chunk 檔案，跳過切分步驟")
            
            # 從現有檔案建立 metadata
            chunk_metadata = []
            for chunk_file in sorted(existing_chunks):
                try:
                    # 解析檔名取得時間資訊
                    parts = chunk_file.stem.split('_')
                    if len(parts) >= 4:
                        start_ms = int(parts[-2])
                        end_ms = int(parts[-1])
                    else:
                        start_ms = 0
                        end_ms = 60000  # 預設值
                    
                    chunk_metadata.append({
                        'file_path': str(chunk_file),
                        'start_time_ms': start_ms,
                        'end_time_ms': end_ms,
                        'duration_ms': end_ms - start_ms,
                        'chunk_id': len(chunk_metadata) + 1
                    })
                except Exception as e:
                    print(f"   ⚠️ 解析檔名失敗 {chunk_file.name}: {e}")
                    continue
            
            for chunk in chunk_metadata:
                duration_sec = chunk['duration_ms'] / 1000
                print(f"   - {Path(chunk['file_path']).name}: {duration_sec:.1f}s")
            
            return chunk_metadata
        
        try:
            # 如果強制重新處理，先清理舊檔案
            if self.force_reprocess and existing_chunks:
                print(f"🗑️ 清理 {len(existing_chunks)} 個舊 chunk 檔案...")
                for chunk_file in existing_chunks:
                    chunk_file.unlink()
                    # 同時清理相關的 JSON 檔案
                    base_name = chunk_file.stem
                    for suffix in ['_whisper.json', '_diar.json', '_aligned.json']:
                        json_file = chunk_file.parent / f"{base_name}{suffix}"
                        if json_file.exists():
                            json_file.unlink()
            
            # 執行音訊切分
            chunk_metadata = self.splitter.split_audio(
                str(self.video_path), 
                num_chunks=num_chunks
            )
            
            print(f"✅ 音訊切分完成，產生 {len(chunk_metadata)} 個片段")
            for chunk in chunk_metadata:
                duration_sec = chunk['duration_ms'] / 1000
                print(f"   - {Path(chunk['file_path']).name}: {duration_sec:.1f}s")
            
            return chunk_metadata
            
        except Exception as e:
            print(f"❌ 音訊切分失敗: {e}")
            raise
    
    def step2_ai_processing(self, chunk_metadata: List[Dict[str, Any]]) -> List[str]:
        """步驟 2-4: AI 處理 (Whisper + Diarization + Alignment)"""
        print(f"\n🤖 [步驟 2-4/6] AI 處理 (Whisper + Diarization + Alignment)...")
        print("=" * 50)
        
        aligned_files = []
        success_count = 0
        
        for i, chunk_info in enumerate(chunk_metadata):
            chunk_path = chunk_info['file_path']
            chunk_name = Path(chunk_path).name
            
            print(f"\n🔄 [{i+1}/{len(chunk_metadata)}] 處理: {chunk_name}")
            
            try:
                # 準備檔案路徑
                base_path = Path(chunk_path).with_suffix('')
                whisper_json = f"{base_path}_whisper.json"
                diar_json = f"{base_path}_diar.json"
                aligned_json = f"{base_path}_aligned.json"
                
                # 檢查是否已完成處理
                if os.path.exists(aligned_json) and not self.force_reprocess:
                    print(f"   ⏩ 已處理完成，跳過: {chunk_name}")
                    aligned_files.append(aligned_json)
                    success_count += 1
                    continue
                
                # 如果強制重新處理，清理舊檔案
                if self.force_reprocess:
                    for json_file in [whisper_json, diar_json, aligned_json]:
                        if os.path.exists(json_file):
                            os.remove(json_file)
                            print(f"   🗑️ 清理舊檔案: {Path(json_file).name}")
                
                # 計算時間偏移
                start_ms = chunk_info['start_time_ms']
                offset_sec = start_ms / 1000.0
                
                # ==========================================
                # Phase 1: Whisper
                # ==========================================
                if not os.path.exists(whisper_json):
                    print(f"   🎧 執行 Whisper...")
                    self.ai_processor.run_whisper(chunk_path, whisper_json)
                    # 🔥 關鍵：跑完一個模型馬上清記憶體，避免跟下一個模型打架
                    self._clean_gpu()
                else:
                    print(f"   ⏭️ Whisper 已存在，跳過。")
                
                # ==========================================
                # Phase 2: Diarization
                # ==========================================
                if not os.path.exists(diar_json):
                    print(f"   🗣️ 執行 Diarization...")
                    self.ai_processor.run_diarization(chunk_path, diar_json)
                    # 🔥 關鍵：再清一次
                    self._clean_gpu()
                else:
                    print(f"   ⏭️ Diarization 已存在，跳過。")
                
                # ==========================================
                # Phase 3: Alignment
                # ==========================================
                print(f"   🔗 執行 Alignment...")
                self.ai_processor.run_alignment(whisper_json, diar_json, aligned_json, offset_sec)
                
                aligned_files.append(aligned_json)
                success_count += 1
                print(f"   ✅ 完成: {chunk_name}")
                
            except KeyboardInterrupt:
                print(f"\n⚠️ 使用者中斷處理")
                print(f"💡 已處理的檔案會保留，下次執行時會自動跳過")
                break
            except Exception as e:
                print(f"   ❌ 處理失敗 {chunk_name}: {e}")
                import traceback
                traceback.print_exc()
                continue
            finally:
                # 確保每個迴圈結束都做一次徹底清理
                self._clean_gpu()
        
        print(f"\n✅ AI 處理完成: {success_count}/{len(chunk_metadata)} 個片段成功")
        return aligned_files
    
    def step3_merge_chunks(self, aligned_files: List[str]) -> List[Dict[str, Any]]:
        """步驟 5: 合併所有 chunk 的結果"""
        print(f"\n🔗 [步驟 5/6] 合併片段...")
        print("=" * 50)
        
        all_segments = []
        
        for aligned_file in aligned_files:
            if not os.path.exists(aligned_file):
                print(f"⚠️ 跳過不存在的檔案: {aligned_file}")
                continue
            
            try:
                with open(aligned_file, 'r', encoding='utf-8') as f:
                    segments = json.load(f)
                
                # 確保每個 segment 都有必要的欄位
                for segment in segments:
                    if 'sentence_id' not in segment:
                        segment['sentence_id'] = len(all_segments)
                    if 'verification_score' not in segment:
                        segment['verification_score'] = 1.0
                    if 'status' not in segment:
                        segment['status'] = 'auto'
                    if 'needs_review' not in segment:
                        segment['needs_review'] = False
                    if 'review_reason' not in segment:
                        segment['review_reason'] = None
                
                all_segments.extend(segments)
                print(f"   📄 載入 {len(segments)} 個片段從 {Path(aligned_file).name}")
                
            except Exception as e:
                print(f"   ❌ 載入失敗 {aligned_file}: {e}")
                continue
        
        # 重新編號 sentence_id
        for i, segment in enumerate(all_segments):
            segment['sentence_id'] = i
        
        print(f"✅ 合併完成，總共 {len(all_segments)} 個片段")
        return all_segments
    
    def step4_stitch_and_flag(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """步驟 6: 文字整理和異常標記"""
        print(f"\n🧵 [步驟 6/6] 文字整理和異常標記...")
        print("=" * 50)
        
        try:
            # 執行文字整理 (Stitch)
            print("🧵 執行文字整理...")
            stitched_segments = run_stitching_logic(segments)
            print(f"   ✅ 文字整理完成: {len(stitched_segments)} 個句子")
            
            # 執行異常標記 (Flag)
            print("🚩 執行異常標記...")
            flagged_segments = run_anomaly_detector(stitched_segments)
            
            # 統計標記結果
            flagged_count = sum(1 for seg in flagged_segments if seg.get('needs_review', False))
            print(f"   ✅ 異常標記完成: {flagged_count} 個片段需要人工檢查")
            
            return flagged_segments
            
        except Exception as e:
            print(f"❌ 文字整理和標記失敗: {e}")
            # 如果失敗，返回原始片段
            return segments
    
    def save_results(self, final_segments: List[Dict[str, Any]]) -> str:
        """儲存最終結果"""
        print(f"\n💾 儲存最終結果...")
        print("=" * 30)
        
        # 準備最終資料結構
        final_data = {
            "case_name": self.case_name,
            "video_file": self.video_path.name,
            "processed_at": datetime.now().isoformat(),
            "total_segments": len(final_segments),
            "flagged_segments": sum(1 for seg in final_segments if seg.get('needs_review', False)),
            "speaker_mapping": {},  # 可以後續手動編輯
            "segments": final_segments
        }
        
        # 儲存到案例目錄
        output_file = self.case_dir / "final_transcript.json"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 結果已儲存: {output_file}")
            
            # 顯示統計資訊
            total_duration = max(seg['end'] for seg in final_segments) if final_segments else 0
            flagged_count = final_data['flagged_segments']
            
            print(f"📊 處理統計:")
            print(f"   🎬 影片長度: {total_duration:.1f} 秒")
            print(f"   📝 總片段數: {len(final_segments)}")
            print(f"   🚩 需檢查片段: {flagged_count}")
            print(f"   ✅ 自動通過: {len(final_segments) - flagged_count}")
            
            return str(output_file)
            
        except Exception as e:
            print(f"❌ 儲存失敗: {e}")
            raise
    
    def run_complete_pipeline(self, num_chunks: int = 4) -> str:
        """執行完整流程"""
        print(f"🚀 開始完整轉錄流程")
        print(f"📹 影片: {self.video_path}")
        print(f"📁 案例: {self.case_name}")
        print(f"🔄 模式: {'強制重新處理' if self.force_reprocess else '斷點續傳'}")
        print("=" * 60)
        
        start_time = datetime.now()
        
        try:
            # 步驟 1: 音訊切分
            chunk_metadata = self.step1_split_audio(num_chunks)
            
            # 步驟 2-4: AI 處理
            aligned_files = self.step2_ai_processing(chunk_metadata)
            
            if not aligned_files:
                raise Exception("沒有成功處理的音訊片段")
            
            # 步驟 5: 合併片段
            all_segments = self.step3_merge_chunks(aligned_files)
            
            if not all_segments:
                raise Exception("沒有可用的轉錄片段")
            
            # 步驟 6: 文字整理和標記
            final_segments = self.step4_stitch_and_flag(all_segments)
            
            # 儲存結果
            output_file = self.save_results(final_segments)
            
            # 計算總耗時
            end_time = datetime.now()
            duration = end_time - start_time
            
            print("\n" + "=" * 60)
            print("🎉 完整流程執行成功！")
            print(f"⏱️  總耗時: {duration}")
            print(f"📄 結果檔案: {output_file}")
            print("=" * 60)
            
            return output_file
            
        except KeyboardInterrupt:
            print(f"\n⚠️ 流程被使用者中斷")
            print(f"💡 已處理的檔案會保留，可以使用相同命令繼續執行")
            raise
        except Exception as e:
            print(f"\n❌ 流程執行失敗: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """主程式入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="NeuroAI 完整轉錄流程")
    parser.add_argument("video_path", help="MP4 影片檔案路徑")
    parser.add_argument("--case-name", help="案例名稱 (可選，預設自動生成)")
    parser.add_argument("--chunks", type=int, default=4, help="音訊切分片段數 (預設: 4)")
    parser.add_argument("--force", action="store_true", help="強制重新處理所有檔案")
    
    args = parser.parse_args()
    
    try:
        # 建立並執行流程
        pipeline = OverallPipeline(args.video_path, args.case_name, force_reprocess=args.force)
        result_file = pipeline.run_complete_pipeline(args.chunks)
        
        print(f"\n✅ 轉錄完成！結果檔案: {result_file}")
        
    except KeyboardInterrupt:
        print(f"\n⚠️ 程式被中斷")
        print(f"💡 提示：下次執行相同命令會自動從中斷處繼續")
        print(f"💡 如要重新開始，請加上 --force 參數")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 執行失敗: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
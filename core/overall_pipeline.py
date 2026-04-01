#!/usr/bin/env python3
"""
完整的 NeuroAI 轉錄流程 (優化版)
包含自動記憶體管理與警告過濾，解決 GPU 卡死問題
執行時需將專案根目錄加入 PYTHONPATH（或 pip install -e .）
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

# 確保專案根在 path，以便 import core（當以 __main__ 或腳本直接執行時）
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# 過濾惱人的警告
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*torchaudio._backend.*")
warnings.filterwarnings("ignore", message=".*TensorFloat-32.*")
warnings.filterwarnings("ignore", message=".*degrees of freedom.*")

from core.config import config
from shared.file_manager import file_manager
from core.split import SmartAudioSplitter
from core.pipeline import PipelinePhase2
from core.stitch import run_stitching_logic, aligned_to_stitch_shape
from core.flag import run_anomaly_detector

class OverallPipeline:
    """完整的轉錄流程管理器"""
    
    def __init__(
        self,
        video_path: str,
        case_name: Optional[str] = None,
        force_reprocess: bool = False,
        skip_stitch: Optional[bool] = None,
    ):
        self.video_path = Path(video_path)
        self.force_reprocess = force_reprocess
        self.skip_stitch = config.skip_stitch if skip_stitch is None else skip_stitch
        
        if not self.video_path.exists():
            raise FileNotFoundError(f"找不到影片檔案: {video_path}")
        
        if case_name is None:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M")
            video_name = self.video_path.stem
            self.case_name = f"{timestamp}-{video_name}"
        else:
            self.case_name = case_name
        
        self.case_dir = file_manager.get_case_dir(self.case_name)
        self.intermediate_dir = file_manager.get_intermediate_dir(self.case_name)
        self.splitter = SmartAudioSplitter(case_name=self.case_name)
        self.ai_processor = PipelinePhase2()
        
        print(f"🎬 初始化完整流程")
        print(f"   📄 影片檔案:  {self.video_path.name}")
        print(f"   📁 案例名稱: {self.case_name}")
        print(f"   📂 輸出目錄: {self.case_dir}")
        print(f"   🔄 強制重新處理: {'是' if force_reprocess else '否'}")
        print(f"   ⏭️ 跳過規則 Stitch (No-Stitch): {'是' if self.skip_stitch else '否'}")

    def _clean_gpu(self):
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

    def step1_split_audio(self, num_chunks: int = 4) -> List[Dict[str, Any]]:
        """步驟 1: 音訊切分"""
        print(f"\n🔪 [步驟 1/6] 音訊切分...")
        print("=" * 50)
        
        # chunks 位於 intermediate 目錄
        existing_chunks = list(self.intermediate_dir.glob("chunk_*.wav"))
        
        if existing_chunks and not self.force_reprocess:
            print(f"⏩ 發現 {len(existing_chunks)} 個現有 chunk 檔案，跳過切分步驟")
            chunk_metadata = []
            for chunk_file in sorted(existing_chunks):
                try:
                    parts = chunk_file.stem.split('_')
                    if len(parts) >= 4:
                        start_ms = int(parts[-2])
                        end_ms = int(parts[-1])
                    else:
                        start_ms = 0
                        end_ms = 60000
                    
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
            if self.force_reprocess and existing_chunks:
                print(f"🗑️ 清理 {len(existing_chunks)} 個舊 chunk 檔案...")
                for chunk_file in existing_chunks:
                    chunk_file.unlink()
                    base_name = chunk_file.stem
                    for suffix in ['_whisper.json', '_diar.json', '_aligned.json']:
                        json_file = chunk_file.parent / f"{base_name}{suffix}"
                        if json_file.exists():
                            json_file.unlink()
            
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
                base_path = Path(chunk_path).with_suffix('')
                whisper_json = str(base_path) + "_whisper.json"
                diar_json = str(base_path) + "_diar.json"
                aligned_json = str(base_path) + "_aligned.json"
                
                if os.path.exists(aligned_json) and not self.force_reprocess:
                    print(f"   ⏩ 已處理完成，跳過: {chunk_name}")
                    aligned_files.append(aligned_json)
                    success_count += 1
                    continue
                
                if self.force_reprocess:
                    for json_file in [whisper_json, diar_json, aligned_json]:
                        if os.path.exists(json_file):
                            os.remove(json_file)
                            print(f"   🗑️ 清理舊檔案: {Path(json_file).name}")
                
                start_ms = chunk_info['start_time_ms']
                offset_sec = start_ms / 1000.0
                
                if not os.path.exists(whisper_json):
                    print(f"   🎧 執行 Whisper...")
                    self.ai_processor.run_whisper_batch([{'wav': chunk_path, 'json': whisper_json}])
                    self._clean_gpu()
                else:
                    print(f"   ⏭️ Whisper 已存在，跳過。")
                
                if not os.path.exists(diar_json):
                    print(
                        f"   🗣️ 執行 Diarization (backend={config.diarization_backend})..."
                    )
                    self.ai_processor.run_diarization_batch(
                        [{"wav": chunk_path, "json": diar_json}]
                    )
                    self._clean_gpu()
                else:
                    print(f"   ⏭️ Diarization 已存在，跳過。")
                
                print(f"   🔗 執行 Alignment...")
                self.ai_processor.run_alignment(whisper_json, diar_json, aligned_json, offset_sec)
                
                aligned_files.append(aligned_json)
                success_count += 1
                print(f"   ✅ 完成: {chunk_name}")
                
            except KeyboardInterrupt:
                print(f"\n⚠️ 使用者中斷處理")
                break
            except Exception as e:
                print(f"   ❌ 處理失敗 {chunk_name}: {e}")
                import traceback
                traceback.print_exc()
                continue
            finally:
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
        
        for i, segment in enumerate(all_segments):
            segment['sentence_id'] = i
        print(f"✅ 合併完成，總共 {len(all_segments)} 個片段")
        return all_segments
    
    def step4_stitch_and_flag(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """步驟 6: 文字整理和異常標記"""
        print(f"\n🧵 [步驟 6/6] 規則併句和異常標記...")
        print("=" * 50)
        try:
            if self.skip_stitch:
                print("🧵 No-Stitch：aligned 合併稿逐段直通...")
                stitched_segments = aligned_to_stitch_shape(segments)
            else:
                print("🧵 執行規則併句...")
                stitched_segments = run_stitching_logic(segments)
            print(f"   ✅ 規則併句完成: {len(stitched_segments)} 個句子")
            print("🚩 執行異常標記...")
            flagged_segments = run_anomaly_detector(stitched_segments)
            flagged_count = sum(1 for seg in flagged_segments if seg.get('needs_review', False))
            print(f"   ✅ 異常標記完成: {flagged_count} 個片段需要人工檢查")
            return flagged_segments
        except Exception as e:
            print(f"❌ 規則併句和標記失敗: {e}")
            return segments
    
    def save_results(self, final_segments: List[Dict[str, Any]]) -> str:
        """儲存最終結果"""
        print(f"\n💾 儲存最終結果...")
        print("=" * 30)
        final_data = {
            "case_name": self.case_name,
            "video_file": self.video_path.name,
            "processed_at": datetime.now().isoformat(),
            "total_segments": len(final_segments),
            "flagged_segments": sum(1 for seg in final_segments if seg.get('needs_review', False)),
            "speaker_mapping": {},
            "segments": final_segments
        }
        output_file = file_manager.get_output_file_path(self.case_name, "final_transcript.json")
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            print(f"✅ 結果已儲存: {output_file}")
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
            chunk_metadata = self.step1_split_audio(num_chunks)
            aligned_files = self.step2_ai_processing(chunk_metadata)
            if not aligned_files:
                raise Exception("沒有成功處理的音訊片段")
            all_segments = self.step3_merge_chunks(aligned_files)
            if not all_segments:
                raise Exception("沒有可用的轉錄片段")
            final_segments = self.step4_stitch_and_flag(all_segments)
            output_file = self.save_results(final_segments)
            duration = datetime.now() - start_time
            print("\n" + "=" * 60)
            print("🎉 完整流程執行成功！")
            print(f"⏱️  總耗時: {duration}")
            print(f"📄 結果檔案: {output_file}")
            print("=" * 60)
            return output_file
        except KeyboardInterrupt:
            print(f"\n⚠️ 流程被使用者中斷")
            raise
        except Exception as e:
            print(f"\n❌ 流程執行失敗: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NeuroAI 完整轉錄流程")
    parser.add_argument("video_path", help="MP4 影片檔案路徑")
    parser.add_argument("--case-name", help="案例名稱 (可選，預設自動生成)")
    parser.add_argument("--chunks", type=int, default=4, help="音訊切分片段數 (預設: 4)")
    parser.add_argument("--force", action="store_true", help="強制重新處理所有檔案")
    parser.add_argument(
        "--no-stitch",
        action="store_true",
        help="跳過規則併句（與 run_pipeline --no-stitch 一致；亦可 SKIP_STITCH=1）",
    )
    args = parser.parse_args()
    
    try:
        pipeline = OverallPipeline(
            args.video_path,
            args.case_name,
            force_reprocess=args.force,
            skip_stitch=True if args.no_stitch else None,
        )
        result_file = pipeline.run_complete_pipeline(args.chunks)
        print(f"\n✅ 轉錄完成！結果檔案: {result_file}")
    except KeyboardInterrupt:
        print(f"\n⚠️ 程式被中斷")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 執行失敗: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

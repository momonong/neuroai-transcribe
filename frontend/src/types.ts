export interface TranscriptSegment {
  start: number;
  end: number;
  speaker: string;
  text: string;
  verification_score: number;
  status: string;
  sentence_id: number;
  needs_review: boolean;
  review_reason: string | null;
  suggested_correction?: string | null;
}

export interface ChunkTimepoint {
  chunk_id: number;
  start_ms: number;
  end_ms: number;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
}

export interface ChunkData {
  speaker_mapping: Record<string, string>;
  segments: TranscriptSegment[];
  media_file?: string;
  video_offset?: number;
  chunk_timepoints?: ChunkTimepoint[];
  file_type?: 'flagged' | 'edited' | 'original';
}

export interface VideoFile {
  path: string;
  name: string;
}
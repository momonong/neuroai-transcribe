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
}

export interface ChunkData {
  speaker_mapping: Record<string, string>;
  segments: TranscriptSegment[];
  media_file?: string;
  video_offset?: number;
}

export interface VideoFile {
  path: string;
  name: string;
}
import React from 'react';
import { Box, TextField, Chip, Tooltip, IconButton, Alert } from '@mui/material';
import { PlayCircleFilled, AccessTime, WarningAmber, AddCircle, Delete } from '@mui/icons-material';
import type { TranscriptSegment } from '../types';

interface Props {
  segment: TranscriptSegment;
  videoOffset: number;
  displaySpeaker: string;
  isDoctor: boolean;
  onTextChange: (id: number, val: string) => void;
  onSyncTime: (index: number) => void;
  onJumpToTime: (start: number) => void;
  onSpeakerClick: (e: React.MouseEvent<HTMLElement>, index: number) => void;
  onDelete: (index: number) => void;   // ★ 新增定義
  onAddAfter: (index: number) => void; // ★ 新增定義
  index: number;
}

const formatTime = (seconds: number) => {
  if (isNaN(seconds)) return "00:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return `${mins}:${secs.toString().padStart(2, '0')}.${ms}`;
};

export const TranscriptItem = React.memo(({ 
  segment, videoOffset, displaySpeaker, isDoctor, 
  onTextChange, onSyncTime, onJumpToTime, onSpeakerClick, onDelete, onAddAfter, index 
}: Props) => {

  const absoluteDisplayTime = videoOffset + segment.start;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onTextChange(segment.sentence_id, e.target.value);
  };

  return (
    <Box sx={{ display: 'flex', gap: 2, mb: 3, position: 'relative', '&:hover .actions': { opacity: 1 } }}>
      
      {/* 左側：時間 */}
      <Box sx={{ pt: 0.5, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.5 }}>
        <Tooltip title="跳轉到此處">
          <Chip
            label={formatTime(absoluteDisplayTime)}
            onClick={() => onJumpToTime(segment.start)}
            size="small"
            icon={<PlayCircleFilled sx={{ fontSize: '14px !important' }} />}
            sx={{
              cursor: 'pointer', bgcolor: '#e2e8f0', fontFamily: 'monospace', fontWeight: 'bold',
              width: '85px', justifyContent: 'flex-start'
            }}
          />
        </Tooltip>

        <Tooltip title="將開始時間重設為目前影片進度">
          <IconButton
            size="small"
            onClick={() => onSyncTime(index)}
            sx={{ color: '#94a3b8', '&:hover': { color: '#2563eb', bgcolor: '#eff6ff' } }}
          >
            <AccessTime fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* 中間：內容 */}
      <Box sx={{ flex: 1 }}>
        <Tooltip title="點擊切換語者">
          <Chip
            label={displaySpeaker}
            size="small"
            onClick={(e) => onSpeakerClick(e, index)}
            sx={{
              mb: 1, fontWeight: 'bold', fontSize: '0.75rem', height: 24,
              bgcolor: isDoctor ? '#ecfdf5' : '#fffbeb',
              color: isDoctor ? '#047857' : '#b45309',
              border: '1px solid',
              borderColor: isDoctor ? '#10b981' : '#f59e0b',
              cursor: 'pointer'
            }}
          />
        </Tooltip>
        
        <TextField
          fullWidth
          multiline
          value={segment.text}
          onChange={handleChange}
          sx={{ bgcolor: 'white', '& .MuiOutlinedInput-root': { p: 1.5 } }}
        />
        
        {segment.needs_review && (
          <Alert severity="warning" icon={<WarningAmber fontSize="inherit" />} sx={{ mt: 1, py: 0, px: 1, fontSize: '0.75rem' }}>
            {segment.review_reason}
          </Alert>
        )}
      </Box>

      {/* 右側：操作按鈕 */}
      <Box className="actions" sx={{ opacity: 0, transition: '0.2s', display: 'flex', flexDirection: 'column', gap: 1, pt: 1 }}>
          <Tooltip title="在此句下方新增">
              <IconButton size="small" color="primary" onClick={() => onAddAfter(index)}>
                  <AddCircle />
              </IconButton>
          </Tooltip>
          <Tooltip title="刪除此句">
              <IconButton size="small" color="error" onClick={() => onDelete(index)}>
                  <Delete />
              </IconButton>
          </Tooltip>
      </Box>
    </Box>
  );
}, (prevProps, nextProps) => {
  return (
    prevProps.segment === nextProps.segment &&
    prevProps.videoOffset === nextProps.videoOffset &&
    prevProps.displaySpeaker === nextProps.displaySpeaker
  );
});
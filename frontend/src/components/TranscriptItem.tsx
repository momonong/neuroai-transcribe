import React, { memo } from 'react';
import { 
  Paper, IconButton, TextField, Typography, Box, 
  Tooltip, Button 
} from '@mui/material';
import { 
  PlayArrow, Sync, Person, Delete, Add, 
  AutoFixHigh, Check, Close 
} from '@mui/icons-material';

import type { TranscriptSegment } from '../types';

interface TranscriptItemProps {
  index: number;
  segment: TranscriptSegment;
  videoOffset: number;
  displaySpeaker: string;
  isDoctor: boolean;
  onTextChange: (index: number, newText: string) => void;
  onSyncTime: (index: number) => void;
  onSyncEndTime: (index: number) => void;
  onJumpToTime: (time: number) => void;
  onSpeakerClick: (event: React.MouseEvent<HTMLElement>, index: number) => void;
  onDelete: (index: number) => void;
  onAddAfter: (index: number) => void;
  onResolveFlag: (index: number, action: 'accept' | 'ignore') => void;
}

// Helper: Format seconds to MM:SS.ss
const formatTimestamp = (totalSeconds: number): string => {
  if (isNaN(totalSeconds) || totalSeconds < 0) return "00:00.00";
  
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  const centiseconds = Math.round((totalSeconds % 1) * 100);

  const mm = minutes.toString().padStart(2, '0');
  const ss = seconds.toString().padStart(2, '0');
  const cs = centiseconds.toString().padStart(2, '0');

  return `${mm}:${ss}.${cs}`;
};

// Wrap component with React.memo to prevent unnecessary re-renders
export const TranscriptItem = memo<TranscriptItemProps>(({
  index, segment, videoOffset, displaySpeaker, isDoctor,
  onTextChange, onSyncTime, onSyncEndTime, onJumpToTime, onSpeakerClick, onDelete, onAddAfter,
  onResolveFlag
}) => {
  
  const absStart = segment.start + videoOffset;
  const absEnd = segment.end + videoOffset;

  const speakerColor = isDoctor ? '#0ea5e9' : '#f59e0b';
  const speakerBg = isDoctor ? 'rgba(14, 165, 233, 0.08)' : 'rgba(245, 158, 11, 0.08)';

  return (
    <Paper 
      elevation={0}
      variant="outlined"
      sx={{ 
        p: 2, 
        mb: 2, 
        display: 'flex', 
        flexDirection: 'column',
        gap: 1.5,
        bgcolor: segment.needs_review ? '#fffbeb' : '#ffffff', 
        border: segment.needs_review ? '1px solid #fcd34d' : '1px solid #e2e8f0',
        borderRadius: 2,
        transition: 'all 0.2s',
        '&:hover': { borderColor: '#cbd5e1', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }
      }}
    >
      {/* 上方一列：語者 + 文字區 + 操作（統一高度、垂直置中） */}
      <Box sx={{ display: 'flex', alignItems: 'stretch', gap: 1.5, minHeight: 44 }}>
        <Box 
          onClick={(e) => onSpeakerClick(e, index)}
          sx={{ 
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 0.75,
            px: 1.25,
            borderRadius: 1.5,
            bgcolor: speakerBg,
            border: `1px solid ${speakerColor}33`,
            flexShrink: 0,
            minHeight: 44,
            '&:hover': { bgcolor: isDoctor ? 'rgba(14, 165, 233, 0.14)' : 'rgba(245, 158, 11, 0.14)' }
          }}
        >
          <Person sx={{ fontSize: 18, color: speakerColor }} />
          <Typography variant="caption" fontWeight={600} sx={{ color: speakerColor, lineHeight: 1 }}>
            {displaySpeaker}
          </Typography>
        </Box>

        <TextField
          fullWidth
          multiline
          minRows={1}
          value={segment.text}
          onChange={(e) => onTextChange(index, e.target.value)}
          variant="outlined"
          size="small"
          sx={{ 
            flex: 1,
            '& .MuiOutlinedInput-root': {
              bgcolor: '#fafafa',
              borderRadius: 1.5,
              minHeight: 44,
              '& .MuiInputBase-input': { py: '12px' },
              '&.Mui-focused': { bgcolor: '#fff' },
              '&.Mui-focused fieldset': {
                borderColor: speakerColor,
                borderWidth: 1.5
              }
            }
          }}
        />

        <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 0.25, flexShrink: 0 }}>
          <Tooltip title="Delete this segment">
            <IconButton onClick={() => onDelete(index)} size="small" sx={{ color: '#94a3b8', '&:hover': { color: '#ef4444', bgcolor: '#fef2f2' } }}>
              <Delete fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Add segment after this">
            <IconButton onClick={() => onAddAfter(index)} size="small" sx={{ color: '#94a3b8', '&:hover': { color: '#0ea5e9', bgcolor: '#f0f9ff' } }}>
              <Add fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* 下方一橫列：時間設定（開始 → 結束，統一高度、垂直置中） */}
      <Box 
        sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          flexWrap: 'wrap',
          gap: 0,
          px: 1.5,
          py: 0,
          minHeight: 40,
          borderRadius: 1.5,
          bgcolor: '#f8fafc',
          border: '1px solid #f1f5f9'
        }}
      >
        {/* 開始時間 */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, py: 0.75 }}>
          <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 600, minWidth: 28, lineHeight: 1 }}>Start</Typography>
          <Tooltip title="Jump to this time and play">
            <IconButton onClick={() => onJumpToTime(absStart)} size="small" sx={{ color: '#0ea5e9', p: 0.4 }}>
              <PlayArrow sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', color: '#475569', fontWeight: 600, minWidth: 52, lineHeight: 1 }}>
            {formatTimestamp(absStart)}
          </Typography>
          <Tooltip title="Set start time to current playback position">
            <IconButton onClick={() => onSyncTime(index)} size="small" sx={{ color: '#64748b', p: 0.4 }}>
              <Sync sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        </Box>

        <Typography component="span" sx={{ mx: 2, color: '#94a3b8', fontWeight: 600, fontSize: '0.85rem', lineHeight: 1 }} aria-hidden>→</Typography>

        {/* 結束時間 */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, py: 0.75 }}>
          <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 600, minWidth: 28, lineHeight: 1 }}>End</Typography>
          <Tooltip title="Jump to this time and play">
            <IconButton onClick={() => onJumpToTime(absEnd)} size="small" sx={{ color: '#0ea5e9', p: 0.4 }}>
              <PlayArrow sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
          <Typography variant="caption" sx={{ fontFamily: 'monospace', color: '#475569', fontWeight: 600, minWidth: 52, lineHeight: 1 }}>
            {formatTimestamp(absEnd)}
          </Typography>
          <Tooltip title="Set end time to current playback position">
            <IconButton onClick={() => onSyncEndTime(index)} size="small" sx={{ color: '#64748b', p: 0.4 }}>
              <Sync sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* AI Suggestion Block */}
      {segment.needs_review && segment.suggested_correction && (
        <Paper 
          variant="outlined" 
          sx={{ 
            p: 1.5, 
            borderRadius: 1.5,
            bgcolor: '#fff', 
            borderColor: '#fdba74', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 1
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1, minWidth: 0 }}>
            <AutoFixHigh sx={{ color: '#ea580c', fontSize: 20 }} />
            <Tooltip title={segment.review_reason || "AI detected potential issue"} arrow placement="top">
              <Typography variant="body2" sx={{ color: '#9a3412', fontWeight: 600, cursor: 'help' }}>
                AI suggestion:
              </Typography>
            </Tooltip>
            <Typography variant="body2" sx={{ color: '#1e293b' }}>
              {segment.suggested_correction}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              color="inherit"
              startIcon={<Close />}
              onClick={() => onResolveFlag(index, 'ignore')}
              sx={{ textTransform: 'none', color: '#64748b' }}
            >
              Ignore
            </Button>
            <Button
              size="small"
              variant="contained"
              startIcon={<Check />}
              onClick={() => onResolveFlag(index, 'accept')}
              sx={{ textTransform: 'none', boxShadow: 'none', bgcolor: '#f97316', '&:hover': { bgcolor: '#ea580c' } }}
            >
              Accept
            </Button>
          </Box>
        </Paper>
      )}
    </Paper>
  );
});
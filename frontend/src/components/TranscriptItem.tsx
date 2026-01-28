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
  onTextChange, onSyncTime, onJumpToTime, onSpeakerClick, onDelete, onAddAfter,
  onResolveFlag
}) => {
  
  const absStart = segment.start + videoOffset;

  return (
    <Paper 
      elevation={1} 
      sx={{ 
        p: 2, 
        mb: 2, 
        display: 'flex', 
        gap: 2,
        bgcolor: segment.needs_review ? '#fffbeb' : 'white', 
        border: segment.needs_review ? '1px solid #fcd34d' : '1px solid transparent',
        transition: 'all 0.2s',
        '&:hover': { boxShadow: 3 }
      }}
    >
      {/* Left Control Area */}
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, minWidth: '100px' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Tooltip title="Jump to time">
            <IconButton onClick={() => onJumpToTime(absStart)} color="primary" size="small">
              <PlayArrow />
            </IconButton>
          </Tooltip>
          <Tooltip title="Sync timestamp">
            <IconButton onClick={() => onSyncTime(index)} size="small" sx={{ color: '#64748b' }}>
              <Sync fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        
        <Typography variant="caption" sx={{ fontFamily: 'monospace', color: '#64748b', mt: -0.5, fontWeight: 'bold' }}>
          {formatTimestamp(absStart)}
        </Typography>
        
        <Box 
          onClick={(e) => onSpeakerClick(e, index)}
          sx={{ 
            cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center',
            p: 0.5, borderRadius: 1, '&:hover': { bgcolor: '#f1f5f9' }, mt: 0.5
          }}
        >
          <Person fontSize="small" sx={{ color: isDoctor ? '#0ea5e9' : '#f59e0b' }} />
          <Typography variant="caption" fontWeight="bold" sx={{ color: isDoctor ? '#0ea5e9' : '#f59e0b', maxWidth: '80px', textAlign: 'center' }}>
            {displaySpeaker}
          </Typography>
        </Box>
      </Box>

      {/* Middle Text Area */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
        <TextField
          fullWidth
          multiline
          minRows={1}
          value={segment.text}
          onChange={(e) => onTextChange(index, e.target.value)}
          variant="outlined"
          sx={{ 
            bgcolor: 'white',
            '& .MuiOutlinedInput-root': {
              '&.Mui-focused fieldset': {
                borderColor: isDoctor ? '#0ea5e9' : '#f59e0b',
              }
            }
          }}
        />

        {/* AI Suggestion Block */}
        {segment.needs_review && segment.suggested_correction && (
          <Paper 
            variant="outlined" 
            sx={{ 
              p: 1, px: 2, 
              bgcolor: '#fff', 
              borderColor: '#fdba74', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'space-between',
              animation: 'fadeIn 0.5s ease-in-out'
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <AutoFixHigh sx={{ color: '#ea580c', fontSize: 20 }} />
              
              <Tooltip title={segment.review_reason || "AI detected a potential issue"} arrow placement="top">
                <Typography variant="body2" sx={{ color: '#9a3412', fontWeight: 600, cursor: 'help', borderBottom: '1px dotted #9a3412' }}>
                  AI Suggestion:
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
                  sx={{ 
                    textTransform: 'none', color: '#64748b', borderColor: '#cbd5e1',
                    '&:hover': { bgcolor: '#f1f5f9', borderColor: '#94a3b8' }
                  }}
                >
                  Ignore
                </Button>

                <Button
                  size="small"
                  variant="contained"
                  color="warning"
                  startIcon={<Check />}
                  onClick={() => onResolveFlag(index, 'accept')}
                  sx={{ 
                    textTransform: 'none', boxShadow: 'none', bgcolor: '#f97316',
                    '&:hover': { bgcolor: '#ea580c' }
                  }}
                >
                  Accept
                </Button>
            </Box>
          </Paper>
        )}
      </Box>

      {/* Right Action Area */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <Tooltip title="Delete segment">
          <IconButton onClick={() => onDelete(index)} size="small" color="error">
            <Delete fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Add segment below">
          <IconButton onClick={() => onAddAfter(index)} size="small" color="primary">
            <Add fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
    </Paper>
  );
});
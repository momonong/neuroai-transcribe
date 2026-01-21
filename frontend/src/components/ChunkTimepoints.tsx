import React from 'react';
import { Box, Button, Typography, Chip } from '@mui/material';
import { PlayArrow, Schedule } from '@mui/icons-material';
import type { ChunkTimepoint } from '../types';

interface Props {
  chunkTimepoints: ChunkTimepoint[];
  onJumpToTime: (timeInSeconds: number) => void;
  fileType: 'flagged' | 'edited' | 'original';
}

export const ChunkTimepoints: React.FC<Props> = ({ 
  chunkTimepoints, 
  onJumpToTime, 
  fileType 
}) => {
  const formatTime = (seconds: number): string => {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const getFileTypeColor = () => {
    switch (fileType) {
      case 'flagged': return '#f59e0b'; // amber
      case 'edited': return '#10b981'; // emerald
      default: return '#6b7280'; // gray
    }
  };

  const getFileTypeLabel = () => {
    switch (fileType) {
      case 'flagged': return '需人工檢查';
      case 'edited': return '已編輯';
      default: return '原始版本';
    }
  };

  if (!chunkTimepoints || chunkTimepoints.length === 0) {
    return null;
  }

  return (
    <Box sx={{ p: 2, bgcolor: '#1e293b', borderBottom: '1px solid #334155' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="subtitle2" sx={{ color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 1 }}>
          <Schedule fontSize="small" />
          時間點快速跳轉
        </Typography>
        <Chip 
          label={getFileTypeLabel()}
          size="small"
          sx={{ 
            bgcolor: getFileTypeColor(),
            color: 'white',
            fontSize: '0.75rem'
          }}
        />
      </Box>
      
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        {chunkTimepoints.map((chunk, index) => {
          const quarterLabel = `第 ${index + 1} 段`;
          const timeLabel = `${formatTime(chunk.start_sec)} - ${formatTime(chunk.end_sec)}`;
          const durationLabel = `(${formatTime(chunk.duration_sec)})`;
          
          return (
            <Button
              key={chunk.chunk_id}
              variant="outlined"
              size="small"
              startIcon={<PlayArrow />}
              onClick={() => onJumpToTime(chunk.start_sec)}
              sx={{
                borderColor: '#475569',
                color: '#e2e8f0',
                bgcolor: '#334155',
                '&:hover': {
                  borderColor: '#38bdf8',
                  bgcolor: '#1e293b',
                  color: '#38bdf8'
                },
                minWidth: 'auto',
                flexDirection: 'column',
                alignItems: 'flex-start',
                textAlign: 'left',
                px: 2,
                py: 1
              }}
            >
              <Typography variant="caption" sx={{ fontWeight: 'bold', lineHeight: 1 }}>
                {quarterLabel}
              </Typography>
              <Typography variant="caption" sx={{ fontSize: '0.7rem', opacity: 0.8, lineHeight: 1 }}>
                {timeLabel}
              </Typography>
              <Typography variant="caption" sx={{ fontSize: '0.65rem', opacity: 0.6, lineHeight: 1 }}>
                {durationLabel}
              </Typography>
            </Button>
          );
        })}
      </Box>
      
      {fileType === 'flagged' && (
        <Box sx={{ mt: 2, p: 1.5, bgcolor: '#fbbf24', borderRadius: 1 }}>
          <Typography variant="caption" sx={{ color: '#92400e', fontWeight: 'bold' }}>
            ⚠️ 此檔案包含需要人工檢查的片段，請仔細核對標記為需檢查的內容
          </Typography>
        </Box>
      )}
    </Box>
  );
};
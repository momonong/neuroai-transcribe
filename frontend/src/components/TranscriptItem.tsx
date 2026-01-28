import React from 'react';
import { 
  Paper, IconButton, TextField, Typography, Box, 
  Tooltip, Button 
} from '@mui/material';
import { 
  PlayArrow, Sync, Person, Delete, Add, 
  AutoFixHigh, Check, Close // 引入 Close Icon
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

export const TranscriptItem: React.FC<TranscriptItemProps> = ({
  index, segment, videoOffset, displaySpeaker, isDoctor,
  onTextChange, onSyncTime, onJumpToTime, onSpeakerClick, onDelete, onAddAfter,
  onResolveFlag // 接收新函式
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
        // 只有當 needs_review 為 true 時才變色
        bgcolor: segment.needs_review ? '#fffbeb' : 'white', 
        border: segment.needs_review ? '1px solid #fcd34d' : '1px solid transparent',
        transition: 'all 0.2s',
        '&:hover': { boxShadow: 3 }
      }}
    >
      {/* 左側控制區 (保持不變) */}
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, minWidth: '100px' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Tooltip title="跳轉播放">
            <IconButton onClick={() => onJumpToTime(absStart)} color="primary" size="small">
              <PlayArrow />
            </IconButton>
          </Tooltip>
          <Tooltip title="同步當前影片時間">
            <IconButton onClick={() => onSyncTime(index)} size="small" sx={{ color: '#64748b' }}>
              <Sync fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Typography variant="caption" sx={{ fontFamily: 'monospace', color: '#64748b', mt: -0.5 }}>
          {absStart.toFixed(1)}s
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

      {/* 中間編輯區 */}
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
              
              {/* 把原因藏在 Tooltip 裡，介面更乾淨 */}
              <Tooltip title={segment.review_reason || "AI 偵測到可能的錯誤"} arrow placement="top">
                <Typography variant="body2" sx={{ color: '#9a3412', fontWeight: 600, cursor: 'help', borderBottom: '1px dotted #9a3412' }}>
                  AI 建議：
                </Typography>
              </Tooltip>

              <Typography variant="body2" sx={{ color: '#1e293b' }}>
                {segment.suggested_correction}
              </Typography>
            </Box>
            
            <Box sx={{ display: 'flex', gap: 1 }}>
                {/* 忽略按鈕 (保留原始文字，移除標記) */}
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
                  忽略
                </Button>

                {/* 接受按鈕 (替換文字，移除標記) */}
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
                  一鍵替換
                </Button>
            </Box>
          </Paper>
        )}
      </Box>

      {/* 右側操作區 */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <Tooltip title="刪除此句">
          <IconButton onClick={() => onDelete(index)} size="small" color="error">
            <Delete fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="在此句後新增">
          <IconButton onClick={() => onAddAfter(index)} size="small" color="primary">
            <Add fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
    </Paper>
  );
};
import React from 'react';
import { 
  Paper, IconButton, TextField, Typography, Box, 
  Tooltip, Button 
} from '@mui/material';
import { 
  PlayArrow, Sync, Person, Delete, Add, 
  Warning, AutoFixHigh, Check 
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
}

export const TranscriptItem: React.FC<TranscriptItemProps> = ({
  index, segment, videoOffset, displaySpeaker, isDoctor,
  onTextChange, onSyncTime, onJumpToTime, onSpeakerClick, onDelete, onAddAfter
}) => {
  
  // 計算絕對時間 (用於顯示)
  const absStart = segment.start + videoOffset;

  // 處理接受建議的函式
  const handleAcceptSuggestion = () => {
    if (segment.suggested_correction) {
      onTextChange(index, segment.suggested_correction);
    }
  };

  return (
    <Paper 
      elevation={1} 
      sx={{ 
        p: 2, 
        mb: 2, 
        display: 'flex', 
        gap: 2,
        bgcolor: segment.needs_review ? '#fffbeb' : 'white', // 警告色背景
        border: segment.needs_review ? '1px solid #fcd34d' : '1px solid transparent',
        transition: 'all 0.2s',
        '&:hover': { boxShadow: 3 }
      }}
    >
      {/* === 左側控制區 (播放、同步、時間、說話者) === */}
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, minWidth: '100px' }}>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Tooltip title="跳轉播放">
            <IconButton onClick={() => onJumpToTime(absStart)} color="primary" size="small">
              <PlayArrow />
            </IconButton>
          </Tooltip>
          
          <Tooltip title="同步當前影片時間 (將此句設為目前播放進度)">
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
            cursor: 'pointer', 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center',
            p: 0.5,
            borderRadius: 1,
            '&:hover': { bgcolor: '#f1f5f9' },
            mt: 0.5
          }}
        >
          <Person fontSize="small" sx={{ color: isDoctor ? '#0ea5e9' : '#f59e0b' }} />
          <Typography variant="caption" fontWeight="bold" sx={{ color: isDoctor ? '#0ea5e9' : '#f59e0b', maxWidth: '80px', textAlign: 'center' }}>
            {displaySpeaker}
          </Typography>
        </Box>
      </Box>

      {/* === 中間編輯區 === */}
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

        {/* AI 建議修正區塊 */}
        {segment.needs_review && segment.suggested_correction && (
          <Paper 
            variant="outlined" 
            sx={{ 
              p: 1.5, 
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
              <Typography variant="body2" sx={{ color: '#9a3412', fontWeight: 600 }}>
                AI 建議：
              </Typography>
              <Typography variant="body2" sx={{ color: '#1e293b' }}>
                {segment.suggested_correction}
              </Typography>
            </Box>
            
            <Button
              size="small"
              variant="contained"
              color="warning"
              startIcon={<Check />}
              onClick={handleAcceptSuggestion}
              sx={{ 
                textTransform: 'none', 
                boxShadow: 'none',
                bgcolor: '#f97316',
                '&:hover': { bgcolor: '#ea580c' }
              }}
            >
              一鍵替換
            </Button>
          </Paper>
        )}
        
        {/* 顯示標記原因 */}
        {segment.needs_review && !segment.suggested_correction && (
           <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
             <Warning sx={{ fontSize: 16, color: '#f59e0b' }} />
             <Typography variant="caption" sx={{ color: '#b45309' }}>
               {segment.review_reason || "需人工檢查"}
             </Typography>
           </Box>
        )}
      </Box>

      {/* === 右側操作區 (只剩刪除與新增) === */}
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
        
        {/* ❌ 這裡原本的 Sync 按鈕已經移到左邊了 */}
      </Box>
    </Paper>
  );
};
import { useCallback, useEffect, useState, type MouseEvent } from 'react';
import axios from 'axios';
import { Edit, DeleteOutline, MoreVert } from '@mui/icons-material';
import {
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Switch,
  TextField,
  Typography,
} from '@mui/material';

export type AdminUserRow = {
  id: number;
  username: string;
  real_name: string;
  is_active: boolean;
};

export type AdminProjectRow = {
  id: number;
  name: string;
  description: string | null;
  user_ids: number[];
};

type ToastFn = (msg: string, type: 'success' | 'error' | 'info' | 'warning') => void;

type Props = {
  open: boolean;
  onClose: () => void;
  currentUserId: number;
  onToast: ToastFn;
};

export function AdminProjectDialog({ open, onClose, currentUserId, onToast }: Props) {
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [projects, setProjects] = useState<AdminProjectRow[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [editingProjectId, setEditingProjectId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [projectMenuAnchor, setProjectMenuAnchor] = useState<null | HTMLElement>(null);
  const [projectMenuTarget, setProjectMenuTarget] = useState<AdminProjectRow | null>(null);

  const refreshAll = useCallback(async () => {
    const [uRes, pRes] = await Promise.all([
      axios.get<AdminUserRow[]>('/api/admin/users'),
      axios.get<AdminProjectRow[]>('/api/admin/projects'),
    ]);
    setUsers(uRes.data);
    setProjects(pRes.data);
    setSelectedProjectId((prev) => {
      if (!pRes.data.length) return null;
      if (prev != null && pRes.data.some((p) => p.id === prev)) return prev;
      return pRes.data[0].id;
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        await refreshAll();
      } catch {
        if (!cancelled) onToast('無法載入管理資料', 'error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, refreshAll, onToast]);

  useEffect(() => {
    if (!open) {
      setEditingProjectId(null);
      setNewName('');
      setNewDescription('');
      setProjectMenuAnchor(null);
      setProjectMenuTarget(null);
    }
  }, [open]);

  const closeProjectMenu = () => {
    setProjectMenuAnchor(null);
    setProjectMenuTarget(null);
  };

  const openProjectMenu = (e: MouseEvent<HTMLElement>, p: AdminProjectRow) => {
    e.stopPropagation();
    e.preventDefault();
    setProjectMenuAnchor(e.currentTarget);
    setProjectMenuTarget(p);
  };

  const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? null;

  const beginEditProject = (p: AdminProjectRow) => {
    setEditingProjectId(p.id);
    setNewName(p.name);
    setNewDescription(p.description ?? '');
    setSelectedProjectId(p.id);
  };

  const cancelEditProject = () => {
    setEditingProjectId(null);
    setNewName('');
    setNewDescription('');
  };

  const handleDeleteProject = async (p: AdminProjectRow) => {
    const msg =
      '確定要刪除此專案嗎？此操作將會連帶刪除該專案下的所有媒體資料紀錄，且無法復原！';
    if (!window.confirm(msg)) return;
    setBusy(true);
    try {
      await axios.delete(`/api/admin/projects/${p.id}`);
      if (editingProjectId === p.id) setEditingProjectId(null);
      setNewName('');
      setNewDescription('');
      await refreshAll();
      onToast('專案已刪除', 'success');
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      onToast(ax.response?.data?.detail ?? '刪除專案失敗', 'error');
      await refreshAll();
    } finally {
      setBusy(false);
    }
  };

  const handleSaveOrCreateProject = async () => {
    const name = newName.trim();
    if (!name) {
      onToast('請輸入專案名稱', 'warning');
      return;
    }
    setBusy(true);
    try {
      if (editingProjectId != null) {
        await axios.patch<AdminProjectRow>(`/api/admin/projects/${editingProjectId}`, {
          name,
          description: newDescription.trim() || null,
        });
        setEditingProjectId(null);
        setNewName('');
        setNewDescription('');
        await refreshAll();
        onToast('專案已更新', 'success');
      } else {
        const { data } = await axios.post<AdminProjectRow>('/api/admin/projects', {
          name,
          description: newDescription.trim() || null,
        });
        setNewName('');
        setNewDescription('');
        await refreshAll();
        setSelectedProjectId(data.id);
        onToast('專案已建立', 'success');
      }
    } catch (e: unknown) {
      const ax = e as { response?: { data?: { detail?: string } } };
      onToast(ax.response?.data?.detail ?? (editingProjectId != null ? '更新專案失敗' : '建立專案失敗'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const toggleMember = async (userId: number, checked: boolean) => {
    if (selectedProjectId == null) return;
    setBusy(true);
    try {
      if (checked) {
        await axios.post(`/api/admin/projects/${selectedProjectId}/users/${userId}`);
      } else {
        await axios.delete(`/api/admin/projects/${selectedProjectId}/users/${userId}`);
      }
      await refreshAll();
      onToast(checked ? '已加入專案' : '已從專案移除', 'success');
    } catch (e: unknown) {
      const ax = e as { response?: { data?: { detail?: string } } };
      onToast(ax.response?.data?.detail ?? '更新專案成員失敗', 'error');
      await refreshAll();
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (user: AdminUserRow, makeActive: boolean) => {
    setBusy(true);
    try {
      if (makeActive) {
        await axios.patch(`/api/admin/users/${user.id}/activate`);
      } else {
        await axios.patch(`/api/admin/users/${user.id}/deactivate`);
      }
      await refreshAll();
      onToast(makeActive ? '帳號已啟用' : '帳號已停權', 'success');
    } catch (e: unknown) {
      const ax = e as { response?: { data?: { detail?: string } } };
      onToast(ax.response?.data?.detail ?? '更新帳號狀態失敗', 'error');
      await refreshAll();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>專案與人員管理</DialogTitle>
      <DialogContent dividers sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Paper variant="outlined" sx={{ p: 2, bgcolor: '#f8fafc' }}>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
            {editingProjectId != null ? '編輯專案' : '建立新專案'}
          </Typography>
          <Grid container spacing={2} alignItems="flex-start">
            <Grid size={{ xs: 12, sm: 5 }}>
              <TextField
                label="專案名稱"
                fullWidth
                size="small"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                disabled={busy}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 5 }}>
              <TextField
                label="說明（選填）"
                fullWidth
                size="small"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                disabled={busy}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 2 }} sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
              <Button
                variant="contained"
                fullWidth
                disabled={busy}
                onClick={handleSaveOrCreateProject}
                sx={{ height: 40 }}
              >
                {editingProjectId != null ? '儲存修改' : '建立專案'}
              </Button>
              {editingProjectId != null && (
                <Button size="small" disabled={busy} onClick={cancelEditProject}>
                  取消編輯
                </Button>
              )}
            </Grid>
          </Grid>
        </Paper>

        <Grid container spacing={2} alignItems="stretch">
          <Grid size={{ xs: 12, md: 4 }}>
            <Paper variant="outlined" sx={{ height: '100%', minHeight: 280 }}>
              <Typography variant="subtitle2" sx={{ p: 1.5, fontWeight: 700, borderBottom: '1px solid #e2e8f0' }}>
                專案列表
              </Typography>
              <List dense sx={{ maxHeight: 360, overflow: 'auto' }}>
                {projects.length === 0 ? (
                  <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
                    尚無專案，請先建立。
                  </Typography>
                ) : (
                  projects.map((p) => (
                    <ListItem
                      key={p.id}
                      disablePadding
                      sx={{
                        borderBottom: '1px solid',
                        borderColor: 'divider',
                        '&:last-of-type': { borderBottom: 'none' },
                      }}
                    >
                      <Box sx={{ position: 'relative', width: '100%' }}>
                        <ListItemButton
                          selected={p.id === selectedProjectId}
                          onClick={() => setSelectedProjectId(p.id)}
                          sx={{
                            minWidth: 0,
                            py: 1.25,
                            pr: 5.5,
                            pl: 1.5,
                            alignItems: 'flex-start',
                            textAlign: 'left',
                          }}
                        >
                          <ListItemText
                            primary={p.name}
                            secondary={p.description ?? undefined}
                            primaryTypographyProps={{
                              variant: 'body2',
                              fontWeight: 600,
                              component: 'span',
                            }}
                            secondaryTypographyProps={{
                              variant: 'caption',
                              component: 'div',
                              sx: {
                                mt: 0.5,
                                whiteSpace: 'normal',
                                wordBreak: 'break-word',
                                color: 'text.secondary',
                                lineHeight: 1.45,
                                pr: 0,
                              },
                            }}
                          />
                        </ListItemButton>
                        <IconButton
                          aria-label="專案操作選單"
                          size="small"
                          disabled={busy}
                          onClick={(e) => openProjectMenu(e, p)}
                          sx={{
                            position: 'absolute',
                            top: 2,
                            right: 2,
                            zIndex: 1,
                            color: 'text.secondary',
                            '&:hover': { bgcolor: 'action.hover' },
                          }}
                        >
                          <MoreVert fontSize="small" />
                        </IconButton>
                      </Box>
                    </ListItem>
                  ))
                )}
              </List>
              <Menu
                anchorEl={projectMenuAnchor}
                open={Boolean(projectMenuAnchor)}
                onClose={closeProjectMenu}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                transformOrigin={{ vertical: 'top', horizontal: 'right' }}
                slotProps={{
                  paper: {
                    elevation: 3,
                    sx: { minWidth: 160, mt: 0.5 },
                  },
                }}
              >
                <MenuItem
                  disabled={busy}
                  onClick={() => {
                    if (projectMenuTarget) beginEditProject(projectMenuTarget);
                    closeProjectMenu();
                  }}
                >
                  <ListItemIcon>
                    <Edit fontSize="small" />
                  </ListItemIcon>
                  編輯
                </MenuItem>
                <MenuItem
                  disabled={busy}
                  onClick={() => {
                    const target = projectMenuTarget;
                    closeProjectMenu();
                    if (target) void handleDeleteProject(target);
                  }}
                  sx={{ color: 'error.main' }}
                >
                  <ListItemIcon>
                    <DeleteOutline fontSize="small" color="error" />
                  </ListItemIcon>
                  刪除
                </MenuItem>
              </Menu>
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, md: 8 }}>
            <Paper variant="outlined" sx={{ height: '100%', minHeight: 280 }}>
              <Typography variant="subtitle2" sx={{ p: 1.5, fontWeight: 700, borderBottom: '1px solid #e2e8f0' }}>
                使用者與專案權限
              </Typography>
              <Box sx={{ maxHeight: 360, overflow: 'auto', p: 1 }}>
                {selectedProjectId == null ? (
                  <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>
                    請先選擇專案。
                  </Typography>
                ) : (
                  users.map((u) => {
                    const inProject = selectedProject?.user_ids.includes(u.id) ?? false;
                    const selfRow = u.id === currentUserId;
                    return (
                      <Box
                        key={u.id}
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1,
                          py: 1,
                          px: 1,
                          borderBottom: '1px solid #f1f5f9',
                          flexWrap: 'wrap',
                        }}
                      >
                        <FormControlLabel
                          control={
                            <Checkbox
                              checked={inProject}
                              disabled={busy || selectedProjectId == null}
                              onChange={(_, c) => void toggleMember(u.id, c)}
                            />
                          }
                          label={
                            <Box>
                              <Typography variant="body2" fontWeight={600}>
                                {u.real_name}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                @{u.username}
                                {!u.is_active ? ' · 已停權' : ''}
                              </Typography>
                            </Box>
                          }
                          sx={{ flex: 1, mr: 0, alignItems: 'flex-start' }}
                        />
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <Typography variant="caption" color="text.secondary">
                            停權
                          </Typography>
                          <Switch
                            size="small"
                            checked={u.is_active}
                            disabled={busy || selfRow}
                            onChange={(_, checked) => void toggleActive(u, checked)}
                          />
                          <Typography variant="caption" color="text.secondary">
                            啟用
                          </Typography>
                        </Box>
                      </Box>
                    );
                  })
                )}
              </Box>
            </Paper>
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose}>關閉</Button>
      </DialogActions>
    </Dialog>
  );
}

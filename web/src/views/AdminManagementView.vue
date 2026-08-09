<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useApi } from '@/composables/useApi'

const { requestJson } = useApi()

const activeTab = ref('users')
const loadingUsers = ref(false)
const loadingClasses = ref(false)
const users = ref([])
const classes = ref([])
const teachers = ref([])

const accountModalOpen = ref(false)
const classModalOpen = ref(false)
const scopeModalOpen = ref(false)
const scopeFormOpen = ref(false)
const editingUser = ref(null)
const editingClass = ref(null)
const editingScope = ref(null)
const selectedClass = ref(null)
const scopes = ref([])

const accountForm = ref({})
const classForm = ref({})
const scopeForm = ref({})

const accountColumns = [
  { title: '用户名', dataIndex: 'username', width: 150 },
  { title: '姓名', dataIndex: 'real_name', width: 120 },
  { title: '角色', dataIndex: 'role_code', width: 110 },
  { title: '教师编号', key: 'teacher_no', width: 130 },
  { title: '状态', dataIndex: 'status', width: 100 },
  { title: '操作', key: 'action', width: 100 },
]

const classColumns = [
  { title: '班级编码', dataIndex: 'class_code', width: 140 },
  { title: '班级名称', dataIndex: 'class_name', width: 120 },
  { title: '年级', dataIndex: 'grade_name', width: 120 },
  { title: '班主任', dataIndex: 'head_teacher_name', width: 120 },
  { title: '状态', key: 'enabled', width: 100 },
  { title: '操作', key: 'action', width: 160 },
]

const scopeColumns = [
  { title: '教师编号', dataIndex: 'teacher_no', width: 140 },
  { title: '教师姓名', dataIndex: 'teacher_name', width: 130 },
  { title: '关系', dataIndex: 'relation_type', width: 130 },
  { title: '查看', key: 'can_view_monitor', width: 80 },
  { title: '启动', key: 'can_start_monitor', width: 80 },
  { title: '复盘', key: 'can_review', width: 80 },
  { title: '状态', key: 'enabled', width: 90 },
  { title: '操作', key: 'action', width: 80 },
]

const accountModalTitle = computed(() => (editingUser.value ? '编辑账号' : '新增账号'))
const classModalTitle = computed(() => (editingClass.value ? '编辑班级' : '新增班级'))

function isTeacherAccount() {
  return accountForm.value.role_code === 'TEACHER'
}

function roleText(roleCode) {
  return roleCode === 'ADMIN' ? '系统管理员' : '教师'
}

function relationText(relationType) {
  const map = {
    HEAD_TEACHER: '班主任',
    SUBJECT_TEACHER: '任课教师',
    OBSERVER: '观察员',
  }
  return map[relationType] || relationType
}

async function loadUsers() {
  loadingUsers.value = true
  try {
    const data = await requestJson('/api/admin/users')
    users.value = data.users || []
  } catch (error) {
    message.error(error.message || '账号列表加载失败')
  } finally {
    loadingUsers.value = false
  }
}

async function loadClasses() {
  loadingClasses.value = true
  try {
    const data = await requestJson('/api/admin/classes')
    classes.value = data.classes || []
  } catch (error) {
    message.error(error.message || '班级列表加载失败')
  } finally {
    loadingClasses.value = false
  }
}

async function loadOptions() {
  try {
    const teacherData = await requestJson('/api/admin/teachers')
    teachers.value = (teacherData.teachers || []).filter((teacher) => teacher.status === 'ENABLED')
  } catch (error) {
    message.error(error.message || '管理选项加载失败')
  }
}

function resetAccountForm() {
  accountForm.value = {
    username: '',
    password: '',
    real_name: '',
    phone: '',
    email: '',
    role_code: 'TEACHER',
    teacher_no: '',
    teacher_name: '',
    department: '',
    title: '',
    status: 'ENABLED',
  }
}

function openCreateAccount() {
  editingUser.value = null
  resetAccountForm()
  accountModalOpen.value = true
}

function openEditAccount(row) {
  editingUser.value = row
  accountForm.value = {
    username: row.username,
    password: '',
    real_name: row.real_name,
    phone: row.phone || '',
    email: row.email || '',
    role_code: row.role_code || 'TEACHER',
    teacher_no: row.teacher?.teacher_no || '',
    teacher_name: row.teacher?.teacher_name || row.real_name,
    department: row.teacher?.department || '',
    title: row.teacher?.title || '',
    status: row.status,
  }
  accountModalOpen.value = true
}

async function saveAccount() {
  if (!accountForm.value.real_name || (!editingUser.value && !accountForm.value.username)) {
    message.warning('请填写用户名和姓名')
    return
  }
  if (!editingUser.value && !accountForm.value.password) {
    message.warning('请填写初始密码')
    return
  }
  if (isTeacherAccount() && !accountForm.value.teacher_no) {
    message.warning('教师账号需要填写教师编号')
    return
  }
  try {
    if (editingUser.value) {
      await requestJson(`/api/admin/users/${editingUser.value.id}`, {
        method: 'PUT',
        body: JSON.stringify(accountForm.value),
      })
    } else {
      await requestJson('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify(accountForm.value),
      })
    }
    message.success('账号信息已保存')
    accountModalOpen.value = false
    await Promise.all([loadUsers(), loadOptions()])
  } catch (error) {
    message.error(error.message || '账号保存失败')
  }
}

function resetClassForm() {
  classForm.value = {
    class_code: '',
    class_name: '',
    grade_name: '',
    academic_year: '',
    head_teacher_id: undefined,
    enabled: true,
  }
}

function openCreateClass() {
  editingClass.value = null
  resetClassForm()
  classModalOpen.value = true
}

function openEditClass(row) {
  editingClass.value = row
  classForm.value = {
    class_code: row.class_code,
    class_name: row.class_name,
    grade_name: row.grade_name || '',
    academic_year: row.academic_year || '',
    head_teacher_id: row.head_teacher_id || undefined,
    enabled: row.enabled,
  }
  classModalOpen.value = true
}

async function saveClass() {
  if (!classForm.value.class_code || !classForm.value.class_name) {
    message.warning('请填写班级编码和班级名称')
    return
  }
  try {
    if (editingClass.value) {
      await requestJson(`/api/admin/classes/${editingClass.value.id}`, {
        method: 'PUT',
        body: JSON.stringify(classForm.value),
      })
    } else {
      await requestJson('/api/admin/classes', {
        method: 'POST',
        body: JSON.stringify(classForm.value),
      })
    }
    message.success('班级信息已保存')
    classModalOpen.value = false
    await loadClasses()
  } catch (error) {
    message.error(error.message || '班级保存失败')
  }
}

async function loadScopes() {
  if (!selectedClass.value) return
  try {
    const data = await requestJson(`/api/admin/classes/${selectedClass.value.id}/scopes`)
    scopes.value = data.scopes || []
  } catch (error) {
    message.error(error.message || '班级授权加载失败')
  }
}

async function openScopes(row) {
  selectedClass.value = row
  scopeModalOpen.value = true
  await loadScopes()
}

function resetScopeForm() {
  scopeForm.value = {
    teacher_id: undefined,
    relation_type: 'SUBJECT_TEACHER',
    can_view_monitor: true,
    can_start_monitor: false,
    can_review: true,
    enabled: true,
  }
}

function openCreateScope() {
  editingScope.value = null
  resetScopeForm()
  scopeFormOpen.value = true
}

function openEditScope(row) {
  editingScope.value = row
  scopeForm.value = {
    teacher_id: row.teacher_id,
    relation_type: row.relation_type,
    can_view_monitor: row.can_view_monitor,
    can_start_monitor: row.can_start_monitor,
    can_review: row.can_review,
    enabled: row.enabled,
  }
  scopeFormOpen.value = true
}

async function saveScope() {
  if (!scopeForm.value.teacher_id) {
    message.warning('请选择教师')
    return
  }
  try {
    if (editingScope.value) {
      await requestJson(`/api/admin/class-scopes/${editingScope.value.id}`, {
        method: 'PUT',
        body: JSON.stringify(scopeForm.value),
      })
    } else {
      await requestJson(`/api/admin/classes/${selectedClass.value.id}/scopes`, {
        method: 'POST',
        body: JSON.stringify(scopeForm.value),
      })
    }
    message.success('班级授权已保存')
    scopeFormOpen.value = false
    await loadScopes()
  } catch (error) {
    message.error(error.message || '班级授权保存失败')
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadClasses(), loadOptions()])
})
</script>

<template>
  <div class="admin-view">
    <header class="page-head">
      <div>
        <h1>账号与班级管理</h1>
        <p>维护系统账号、班级基础信息与教师授权范围。</p>
      </div>
    </header>

    <a-tabs v-model:active-key="activeTab">
      <a-tab-pane key="users" tab="账号管理">
        <section class="panel">
          <div class="toolbar">
            <span>系统管理员与教师账号</span>
            <a-space>
              <a-button @click="loadUsers">刷新</a-button>
              <a-button type="primary" @click="openCreateAccount">新增账号</a-button>
            </a-space>
          </div>
          <a-table :columns="accountColumns" :data-source="users" :loading="loadingUsers" :pagination="{ pageSize: 10 }" row-key="id">
            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'role_code'">
                <a-tag :color="record.role_code === 'ADMIN' ? 'purple' : 'blue'">{{ roleText(record.role_code) }}</a-tag>
              </template>
              <template v-else-if="column.key === 'teacher_no'">
                {{ record.teacher?.teacher_no || '-' }}
              </template>
              <template v-else-if="column.dataIndex === 'status'">
                <a-tag :color="record.status === 'ENABLED' ? 'green' : 'default'">
                  {{ record.status === 'ENABLED' ? '启用' : '停用' }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button type="link" @click="openEditAccount(record)">编辑</a-button>
              </template>
            </template>
          </a-table>
        </section>
      </a-tab-pane>

      <a-tab-pane key="classes" tab="班级管理">
        <section class="panel">
          <div class="toolbar">
            <span>班级信息与教师授权</span>
            <a-space>
              <a-button @click="loadClasses">刷新</a-button>
              <a-button type="primary" @click="openCreateClass">新增班级</a-button>
            </a-space>
          </div>
          <a-table :columns="classColumns" :data-source="classes" :loading="loadingClasses" :pagination="{ pageSize: 10 }" row-key="id">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'enabled'">
                <a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-space>
                  <a-button type="link" @click="openEditClass(record)">编辑</a-button>
                  <a-button type="link" @click="openScopes(record)">授权</a-button>
                </a-space>
              </template>
            </template>
          </a-table>
        </section>
      </a-tab-pane>
    </a-tabs>

    <a-modal v-model:open="accountModalOpen" :title="accountModalTitle" :width="620" @ok="saveAccount">
      <a-form layout="vertical" class="modal-form">
        <a-form-item label="账号类型">
          <a-select v-model:value="accountForm.role_code" :disabled="Boolean(editingUser)">
            <a-select-option value="TEACHER">教师</a-select-option>
            <a-select-option value="ADMIN">系统管理员</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="用户名">
          <a-input v-model:value="accountForm.username" :disabled="Boolean(editingUser)" />
        </a-form-item>
        <a-form-item :label="editingUser ? '新密码' : '初始密码'">
          <a-input-password v-model:value="accountForm.password" :placeholder="editingUser ? '留空则保持原密码' : '至少 8 位'" />
        </a-form-item>
        <a-form-item label="姓名"><a-input v-model:value="accountForm.real_name" /></a-form-item>
        <a-form-item label="手机号"><a-input v-model:value="accountForm.phone" /></a-form-item>
        <a-form-item label="邮箱"><a-input v-model:value="accountForm.email" /></a-form-item>
        <template v-if="isTeacherAccount()">
          <a-form-item label="教师编号"><a-input v-model:value="accountForm.teacher_no" /></a-form-item>
          <a-form-item label="教师姓名"><a-input v-model:value="accountForm.teacher_name" /></a-form-item>
          <a-form-item label="所属部门"><a-input v-model:value="accountForm.department" /></a-form-item>
          <a-form-item label="职称"><a-input v-model:value="accountForm.title" /></a-form-item>
        </template>
        <a-form-item label="账号状态">
          <a-select v-model:value="accountForm.status">
            <a-select-option value="ENABLED">启用</a-select-option>
            <a-select-option value="DISABLED">停用</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="classModalOpen" :title="classModalTitle" :width="620" @ok="saveClass">
      <a-form layout="vertical" class="modal-form">
        <a-form-item label="班级编码"><a-input v-model:value="classForm.class_code" /></a-form-item>
        <a-form-item label="班级名称"><a-input v-model:value="classForm.class_name" /></a-form-item>
        <a-form-item label="年级"><a-input v-model:value="classForm.grade_name" /></a-form-item>
        <a-form-item label="学年"><a-input v-model:value="classForm.academic_year" placeholder="例如：2026-2027" /></a-form-item>
        <a-form-item label="班主任">
          <a-select v-model:value="classForm.head_teacher_id" allow-clear placeholder="可选">
            <a-select-option v-for="teacher in teachers" :key="teacher.id" :value="teacher.id">
              {{ teacher.teacher_no }} · {{ teacher.teacher_name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="启用状态"><a-switch v-model:checked="classForm.enabled" checked-children="启用" un-checked-children="停用" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="scopeModalOpen" :title="`${selectedClass?.class_name || ''} 教师授权`" :width="900" :footer="null">
      <div class="toolbar modal-toolbar">
        <span>设置教师查看、启动监控和保存复盘的权限。</span>
        <a-button type="primary" @click="openCreateScope">新增授权</a-button>
      </div>
      <a-table :columns="scopeColumns" :data-source="scopes" :pagination="false" row-key="id" size="small">
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'relation_type'">{{ relationText(record.relation_type) }}</template>
          <template v-else-if="['can_view_monitor', 'can_start_monitor', 'can_review'].includes(column.key)">
            <a-tag :color="record[column.key] ? 'green' : 'default'">{{ record[column.key] ? '允许' : '禁止' }}</a-tag>
          </template>
          <template v-else-if="column.key === 'enabled'">
            <a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag>
          </template>
          <template v-else-if="column.key === 'action'"><a-button type="link" @click="openEditScope(record)">编辑</a-button></template>
        </template>
      </a-table>
    </a-modal>

    <a-modal v-model:open="scopeFormOpen" :title="editingScope ? '编辑教师授权' : '新增教师授权'" :width="540" @ok="saveScope">
      <a-form layout="vertical" class="modal-form">
        <a-form-item label="教师">
          <a-select v-model:value="scopeForm.teacher_id" :disabled="Boolean(editingScope)" placeholder="选择教师">
            <a-select-option v-for="teacher in teachers" :key="teacher.id" :value="teacher.id">
              {{ teacher.teacher_no }} · {{ teacher.teacher_name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="班级关系">
          <a-select v-model:value="scopeForm.relation_type">
            <a-select-option value="HEAD_TEACHER">班主任</a-select-option>
            <a-select-option value="SUBJECT_TEACHER">任课教师</a-select-option>
            <a-select-option value="OBSERVER">观察员</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="查看监控"><a-checkbox v-model:checked="scopeForm.can_view_monitor">允许查看实时与历史监控</a-checkbox></a-form-item>
        <a-form-item label="启动监控"><a-checkbox v-model:checked="scopeForm.can_start_monitor">允许启动或切换监控</a-checkbox></a-form-item>
        <a-form-item label="保存复盘"><a-checkbox v-model:checked="scopeForm.can_review">允许保存教学复盘</a-checkbox></a-form-item>
        <a-form-item label="授权状态"><a-switch v-model:checked="scopeForm.enabled" checked-children="启用" un-checked-children="停用" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.admin-view {
  height: 100%;
  padding: 20px;
  overflow: auto;
}
.page-head {
  margin-bottom: 16px;
}
h1, p { margin: 0; }
h1 { color: var(--text-primary); font-size: 24px; }
p { margin-top: 6px; color: var(--text-muted); }
.panel {
  padding: 16px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  color: var(--text-secondary);
}
.modal-toolbar { margin-bottom: 12px; }
@media (max-width: 760px) {
  .admin-view { padding: 12px; }
  .toolbar { align-items: flex-start; flex-direction: column; }
}
</style>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { LockOutlined, UserOutlined } from '@ant-design/icons-vue'
import { useApi, saveAuth } from '@/composables/useApi'

const { requestJson } = useApi()
const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!username.value || !password.value) {
    message.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const data = await requestJson('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    saveAuth(data)
    message.success('登录成功')
    router.replace(route.query.redirect || '/monitor')
  } catch (error) {
    message.error(error.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-view">
    <section class="login-panel">
      <div class="brand-mark">课堂监测</div>
      <h1>登录</h1>
      <div class="form-stack">
        <a-input v-model:value="username" size="large" placeholder="用户名" @keydown.enter="handleLogin">
          <template #prefix><UserOutlined /></template>
        </a-input>
        <a-input-password v-model:value="password" size="large" placeholder="密码" @keydown.enter="handleLogin">
          <template #prefix><LockOutlined /></template>
        </a-input-password>
        <a-button type="primary" size="large" block :loading="loading" @click="handleLogin">登录系统</a-button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-view {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: var(--bg-primary);
}
.login-panel {
  width: min(420px, 100%);
  padding: 32px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}
.brand-mark {
  width: fit-content;
  margin-bottom: 18px;
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-weight: 700;
}
h1 {
  margin: 0 0 24px;
  font-size: 28px;
  color: var(--text-primary);
}
.form-stack {
  display: grid;
  gap: 14px;
}
</style>

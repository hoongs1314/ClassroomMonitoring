import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken, getStoredUser } from '@/composables/useApi'
import MainLayout from '@/layouts/MainLayout.vue'
import LoginView from '@/views/LoginView.vue'
import MonitorView from '@/views/MonitorView.vue'
import HistoryView from '@/views/HistoryView.vue'
import SessionReviewView from '@/views/SessionReviewView.vue'
import AdminManagementView from '@/views/AdminManagementView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    {
      path: '/',
      component: MainLayout,
      redirect: '/monitor',
      children: [
        { path: 'monitor', name: 'monitor', component: MonitorView },
        { path: 'history', name: 'history', component: HistoryView },
        { path: 'review', name: 'review', component: SessionReviewView },
        { path: 'admin', name: 'admin', component: AdminManagementView, meta: { admin: true } },
      ],
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.public) return true
  if (!getAccessToken()) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.admin && !getStoredUser()?.roles?.includes('ADMIN')) return { name: 'monitor' }
  return true
})

export default router

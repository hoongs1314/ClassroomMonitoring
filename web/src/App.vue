<script setup>
import { theme } from 'ant-design-vue'
import MainLayout from '@/layouts/MainLayout.vue'

const themeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#3B82F6',
    colorSuccess: '#22C55E',
    colorWarning: '#F59E0B',
    colorError: '#EF4444',
    colorInfo: '#3B82F6',
    colorBgBase: '#0B0F17',
    colorTextBase: '#E2E8F0',
    borderRadius: 10,
    fontFamily: '"Fira Sans", "Microsoft YaHei", "PingFang SC", sans-serif',
    fontFamilyCode: '"Fira Code", "Consolas", monospace',
    wireframe: true,
  },
}
</script>

<template>
  <a-config-provider :theme="themeConfig">
    <MainLayout />
  </a-config-provider>
</template>

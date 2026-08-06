import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveApiBase, resolveWebSocketBase } from '../src/composables/apiBase.js'

test('开发环境未配置地址时使用本地后端', () => {
  assert.equal(resolveApiBase('', true), 'http://localhost:8997')
})

test('生产环境未配置地址时使用同源反向代理', () => {
  assert.equal(resolveApiBase('', false), '')
})

test('显式 API 地址会去除末尾斜杠', () => {
  assert.equal(resolveApiBase(' https://monitor.example.com/api/ ', false), 'https://monitor.example.com/api')
})

test('WebSocket 地址与 HTTP 或 HTTPS 地址保持同源协议', () => {
  assert.equal(resolveWebSocketBase('http://localhost:8997', ''), 'ws://localhost:8997')
  assert.equal(resolveWebSocketBase('', 'https://monitor.example.com'), 'wss://monitor.example.com')
})

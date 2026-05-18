import { createApp } from 'vue'
import App from './App.vue'
import {
  Button, Modal, Spin, Tag, ConfigProvider, Layout, Menu,
  Input, Select, DatePicker, Table, Badge, Card, Tooltip,
  Drawer, Switch, Slider, Divider, Radio, Empty,
} from 'ant-design-vue'
import router from './router'

import 'ant-design-vue/dist/reset.css'
import './assets/styles/variables.css'
import './assets/styles/base.css'

const app = createApp(App)

app.use(router)

app.use(Button)
app.use(Modal)
app.use(Spin)
app.use(Tag)
app.use(ConfigProvider)
app.use(Layout)
app.use(Menu)
app.use(Input)
app.use(Select)
app.use(DatePicker)
app.use(Table)
app.use(Badge)
app.use(Card)
app.use(Tooltip)
app.use(Drawer)
app.use(Switch)
app.use(Slider)
app.use(Divider)
app.use(Radio)
app.use(Empty)

app.mount('#app')

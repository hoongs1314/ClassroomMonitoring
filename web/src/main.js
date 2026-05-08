import { createApp } from 'vue'
import App from './App.vue'
import { Button, Modal, Spin, Tag, ConfigProvider } from "ant-design-vue";
import router from './router'
import "ant-design-vue/dist/reset.css";

const app = createApp(App)

app.use(router)

app.use(Button);
app.use(Modal);
app.use(Spin);
app.use(Tag);
app.use(ConfigProvider);
app.mount('#app');

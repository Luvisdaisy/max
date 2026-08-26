import { computed, createApp, onMounted, onUnmounted, ref, watch } from "vue";
import { createRouter, createWebHistory, useRoute, useRouter } from "vue-router";
import "./style.css";

const sections = [
  ["home", "工作台"], ["inbox", "收件箱"], ["projects", "项目"],
  ["tasks", "任务"], ["calendar", "日历"], ["automation", "自动化"],
  ["team", "团队"], ["reports", "报表"], ["settings", "设置"],
];

const request = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options,
  });
  if (!response.ok) throw new Error((await response.json()).detail || "请求失败");
  return response.status === 204 ? null : response.json();
};

const routes = sections.map(([section]) => ({
  path: `/arena/${section}`, name: section, component: { template: "<span />" },
}));
routes.push({ path: "/", redirect: "/arena/home" });
const router = createRouter({ history: createWebHistory(), routes });

const App = {
  setup() {
    const route = useRoute(); const router = useRouter();
    const state = ref({ items: [], page: 1, page_size: 6, total: 0 });
    const summary = ref({ counts: {}, projects: [], members: [], automations: [], events: [], metrics: [], settings: {} });
    const progress = ref({ status: "ready", completed: 0, total: 0 });
    const selected = ref([]); const search = ref(""); const priority = ref("all");
    const sort = ref("updated_desc"); const active = ref(null); const editor = ref(null);
    const confirmation = ref(null); const notice = ref("");
    const section = computed(() => String(route.name || "home"));
    const title = computed(() => sections.find(([key]) => key === section.value)?.[1] || "工作台");
    const pageCount = computed(() => Math.max(1, Math.ceil(state.value.total / state.value.page_size)));

    const loadItems = async (page = state.value.page) => {
      const query = new URLSearchParams({ page, query: search.value, priority: priority.value, sort: sort.value });
      state.value = await request(`/api/arena/items?${query}`);
      selected.value = selected.value.filter((id) => state.value.items.some((item) => item.id === id));
    };
    const loadSummary = async () => { summary.value = await request("/api/arena/summary"); };
    const pollProgress = async () => { progress.value = await request("/api/progress"); };
    const navigate = async (target) => {
      try {
        await request("/api/arena/navigation", { method: "POST", body: JSON.stringify({ section: target }) });
        await router.push(`/arena/${target}`);
      } catch (error) { notice.value = error.message; }
    };
    const start = async (taskCount) => {
      try { await request("/api/start", { method: "POST", body: JSON.stringify({ task_count: taskCount }) }); await pollProgress(); }
      catch (error) { notice.value = error.message; }
    };
    const interrupt = async () => {
      try { await request("/api/interrupt", { method: "POST" }); notice.value = "已请求中断，当前题结束后停止后续评测。"; await pollProgress(); }
      catch (error) { notice.value = error.message; }
    };
    const openItem = async (item) => { active.value = await request(`/api/arena/view/${item.id}`, { method: "POST" }); };
    const save = async () => {
      const method = editor.value.id ? "PUT" : "POST";
      const path = editor.value.id ? `/api/arena/items/${editor.value.id}` : "/api/arena/items";
      try {
        await request(path, { method, body: JSON.stringify(editor.value) }); editor.value = null;
        notice.value = "已保存"; await Promise.all([loadItems(1), loadSummary()]);
      } catch (error) { notice.value = error.message; }
    };
    const batch = async (action) => {
      if (!selected.value.length) return;
      if (action === "delete") {
        confirmation.value = { action, title: "确认删除", content: `将删除 ${selected.value.length} 条任务，删除后无法恢复。` }; return;
      }
      await request("/api/arena/batch", { method: "POST", body: JSON.stringify({ ids: selected.value, action, priority: "high" }) });
      notice.value = "批量操作已完成"; await Promise.all([loadItems(), loadSummary()]);
    };
    const confirm = async () => {
      await request("/api/arena/batch", { method: "POST", body: JSON.stringify({ ids: selected.value, action: confirmation.value.action }) });
      confirmation.value = null; selected.value = []; notice.value = "已删除";
      await Promise.all([loadItems(), loadSummary()]);
    };
    const toggleAutomation = async (rule) => {
      await request(`/api/arena/automations/${rule.id}`, { method: "POST", body: JSON.stringify({ enabled: !rule.enabled }) });
      await loadSummary();
    };
    const updateSettings = async (payload) => {
      await request("/api/arena/settings", { method: "POST", body: JSON.stringify(payload) });
      notice.value = "设置已保存"; await loadSummary();
    };
    const onKeydown = (event) => {
      if (event.key === "Escape" && progress.value.status === "running") { event.preventDefault(); void interrupt(); }
    };
    watch(section, () => { active.value = null; notice.value = ""; });
    onMounted(async () => {
      window.addEventListener("keydown", onKeydown);
      await Promise.all([loadItems(1), loadSummary(), pollProgress()]); window.setInterval(pollProgress, 2000);
    });
    onUnmounted(() => window.removeEventListener("keydown", onKeydown));
    return { sections, section, title, state, summary, progress, selected, search, priority, sort, active, editor, confirmation, notice, pageCount, navigate, loadItems, start, interrupt, openItem, save, batch, confirm, toggleAutomation, updateSettings };
  },
  template: `
    <main class="shell">
      <aside class="nav"><h1>星轨协作</h1><p>本地 GUI Agent 评测场</p>
        <button v-for="entry in sections" :key="entry[0]" :class="{active: section===entry[0]}" @click="navigate(entry[0])">{{ entry[1] }}</button>
        <footer>离线环境 · 数据可重置</footer>
      </aside>
      <section class="workspace">
        <header><div><span class="eyebrow">星轨协作 / {{ title }}</span><h2>{{ title }}</h2><p>通过可见界面完成项目协作工作。</p></div><span v-if="notice" class="notice">{{ notice }}</span></header>
        <template v-if="section==='home'">
          <section class="hero"><div><span class="eyebrow">今日概览</span><h3>让团队工作保持清晰</h3><p>从左侧导航进入各业务模块，处理任务、项目和自动化流程。</p></div><div class="date-card">8 月 26 日<br><b>星期三</b></div></section>
          <section class="stats"><article v-for="(value,key) in summary.counts" :key="key"><span>{{ key }}</span><strong>{{ value }}</strong></article></section>
          <section class="panel"><div class="section-title"><div><h3>评测运行</h3><p>选择固定冒烟集或完整任务集。</p></div><span>状态：{{ progress.status }}　{{ progress.completed }}/{{ progress.total || '未选择' }}</span></div><div class="actions"><button class="primary" @click="start(10)">运行 10 条</button><button @click="start(100)">运行 100 条</button><button v-if="progress.status==='running'||progress.status==='interrupting'" class="danger" @click="interrupt">中断（Esc）</button></div></section>
          <section class="grid-two"><article class="panel"><h3>重点项目</h3><button v-for="project in summary.projects.slice(0,3)" :key="project.name" class="project-row" @click="navigate('projects')"><span><b>{{ project.name }}</b><small>{{ project.owner }} 负责</small></span><strong>{{ project.progress }}%</strong></button></article><article class="panel"><h3>近期日程</h3><button v-for="event in summary.events" :key="event.title" class="event-row" @click="navigate('calendar')"><span>{{ event.date }}</span><b>{{ event.title }}</b></button></article></section>
        </template>
        <template v-else-if="section==='inbox'"><section class="panel inbox-list"><button v-for="item in state.items.slice(0,5)" :key="item.id" @click="openItem(item)"><span class="dot" :class="item.priority"></span><span><b>{{ item.name }}</b><small>{{ item.owner }} · {{ item.status }}</small></span><time>{{ item.updated_at }}</time></button></section></template>
        <template v-else-if="section==='projects'"><section class="card-grid"><article v-for="project in summary.projects" :key="project.name" class="project-card"><div class="project-icon">{{ project.name.slice(0,1) }}</div><h3>{{ project.name }}</h3><p>{{ project.owner }} 负责 · {{ project.overdue }} 项逾期</p><div class="progress"><i :style="{width:project.progress+'%'}"></i></div><strong>{{ project.progress }}%</strong><button @click="navigate('tasks')">查看项目任务</button></article></section></template>
        <template v-else-if="section==='tasks'">
          <section class="filters"><input v-model="search" @keyup.enter="loadItems(1)" placeholder="搜索任务名称或负责人" /><select v-model="priority"><option value="all">全部优先级</option><option value="high">高</option><option value="normal">普通</option><option value="low">低</option></select><select v-model="sort"><option value="updated_desc">最近更新</option><option value="name">名称</option></select><button @click="loadItems(1)">筛选</button><button class="primary" @click="editor={name:'',owner:'',priority:'normal',status:'待处理',description:''}">新建任务</button></section>
          <section class="toolbar"><span>已选择 {{ selected.length }} 项</span><button @click="batch('priority')">设为高优先级</button><button @click="batch('complete')">标为完成</button><button class="danger" @click="batch('delete')">删除</button></section>
          <table><thead><tr><th></th><th>任务名称</th><th>负责人</th><th>状态</th><th>优先级</th><th>更新时间</th></tr></thead><tbody><tr v-for="item in state.items" :key="item.id"><td><input type="checkbox" :value="item.id" v-model="selected" /></td><td><button class="link" @click="openItem(item)">{{ item.name }}</button></td><td>{{ item.owner }}</td><td><span class="tag">{{ item.status }}</span></td><td>{{ item.priority }}</td><td>{{ item.updated_at }}</td></tr></tbody></table>
          <footer class="pager"><span>共 {{ state.total }} 条</span><button :disabled="state.page===1" @click="loadItems(state.page-1)">上一页</button><span>{{ state.page }} / {{ pageCount }}</span><button :disabled="state.page===pageCount" @click="loadItems(state.page+1)">下一页</button></footer>
        </template>
        <template v-else-if="section==='calendar'"><section class="calendar"><article v-for="event in summary.events" :key="event.title"><span>{{ event.date }}</span><div><small>{{ event.kind }}</small><h3>{{ event.title }}</h3></div></article></section></template>
        <template v-else-if="section==='automation'"><section class="panel rule-list"><article v-for="rule in summary.automations" :key="rule.id"><div><h3>{{ rule.name }}</h3><p>满足条件时自动执行，无需离开当前工作区。</p></div><button :class="{primary:rule.enabled}" @click="toggleAutomation(rule)">{{ rule.enabled ? '已启用' : '启用' }}</button></article></section></template>
        <template v-else-if="section==='team'"><section class="card-grid"><article v-for="member in summary.members" :key="member.name" class="member-card"><div class="avatar">{{ member.name.slice(0,1) }}</div><h3>{{ member.name }}</h3><p>{{ member.role }}</p><span>{{ member.workload }}</span></article></section></template>
        <template v-else-if="section==='reports'"><section class="stats report-stats"><article v-for="metric in summary.metrics" :key="metric.label" tabindex="0"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong><small>{{ metric.detail }}</small></article></section><section class="panel chart"><h3>最近六周完成趋势</h3><div class="bars"><i v-for="height in [42,58,49,72,66,84]" :key="height" :style="{height:height+'%'}"></i></div></section></template>
        <template v-else-if="section==='settings'"><section class="panel settings"><h3>外观</h3><label>主题<select :value="summary.settings.theme" @change="updateSettings({theme:$event.target.value})"><option>浅色</option><option>深色</option></select></label><label class="switch-row"><span><b>紧凑布局</b><small>在列表中显示更多内容</small></span><input type="checkbox" :checked="summary.settings.compact" @change="updateSettings({compact:$event.target.checked})" /></label></section></template>
      </section>
      <aside class="detail"><h3>详情</h3><template v-if="active"><p><b>{{ active.name }}</b></p><dl><dt>负责人</dt><dd>{{ active.owner }}</dd><dt>状态</dt><dd>{{ active.status }}</dd><dt>描述</dt><dd>{{ active.description }}</dd></dl><button @click="editor={...active}">编辑任务</button></template><p v-else>选择一条记录以查看详情。</p></aside>
      <div v-if="editor" class="modal"><form @submit.prevent="save"><h3>{{ editor.id ? '编辑任务' : '新建任务' }}</h3><label>名称<input v-model="editor.name" /></label><label>负责人<select v-model="editor.owner"><option value="">请选择</option><option v-for="member in summary.members" :key="member.name">{{ member.name }}</option></select></label><label>优先级<select v-model="editor.priority"><option value="high">高</option><option value="normal">普通</option><option value="low">低</option></select></label><label>状态<select v-model="editor.status"><option>待处理</option><option>进行中</option><option>已完成</option><option>已逾期</option></select></label><label>描述<textarea v-model="editor.description"></textarea></label><div><button type="button" @click="editor=null">取消</button><button class="primary" type="submit">保存</button></div></form></div>
      <div v-if="confirmation" class="modal"><section class="confirm"><h3>{{ confirmation.title }}</h3><p>{{ confirmation.content }}</p><div><button @click="confirmation=null">取消</button><button class="danger" @click="confirm">确认删除</button></div></section></div>
    </main>`,
};

createApp(App).use(router).mount("#app");

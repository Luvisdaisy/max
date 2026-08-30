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
    const state = ref({ items: [], page: 1, page_size: 6, total: 0, has_filters: false });
    const summary = ref({ counts: {}, projects: [], members: [], automations: [], activity: [], events: [], metrics: [], settings: {} });
    const progress = ref({ status: "ready", completed: 0, total: 0 });
    const selected = ref([]); const search = ref(""); const priority = ref("all"); const assignee = ref("all");
    const sort = ref("updated_desc"); const active = ref(null); const editor = ref(null);
    const confirmation = ref(null); const notice = ref(""); const projectDetail = ref(null); const loading = ref(true); const error = ref(""); const undoAvailable = ref(false); let progressTimer = null;
    const section = computed(() => String(route.name || "home"));
    const title = computed(() => sections.find(([key]) => key === section.value)?.[1] || "工作台");
    const pageCount = computed(() => Math.max(1, Math.ceil(state.value.total / state.value.page_size)));

    const loadItems = async (page = state.value.page) => {
      loading.value = true;
      const query = new URLSearchParams({ page, query: search.value, priority: priority.value, assignee: assignee.value, sort: sort.value });
      try {
        state.value = await request(`/api/arena/items?${query}`);
        selected.value = selected.value.filter((id) => state.value.items.some((item) => item.id === id));
      } catch (caught) { error.value = caught.message; } finally { loading.value = false; }
    };
    const loadSummary = async () => { try { summary.value = await request("/api/arena/summary"); } catch (caught) { error.value = caught.message; } };
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
    const openItem = async (item) => { try { projectDetail.value = null; active.value = await request(`/api/arena/view/${item.id}`, { method: "POST" }); } catch (caught) { error.value = caught.message; } };
    const openProject = async (project) => { try { await request("/api/arena/navigation", { method: "POST", body: JSON.stringify({ section: "projects" }) }); active.value = null; projectDetail.value = await request(`/api/arena/projects/${encodeURIComponent(project.name)}`); } catch (caught) { error.value = caught.message; } };
    const openProjectTask = async (item) => {
      try {
        active.value = await request(`/api/arena/projects/${encodeURIComponent(projectDetail.value.name)}/tasks/${item.id}`, { method: "POST" });
        await router.push("/arena/tasks"); projectDetail.value = null;
      } catch (caught) { error.value = caught.message; }
    };
    const openEditor = (item) => {
      editor.value = {
        ...item,
        expected_version: item.version,
        tags_text: (item.tags || []).join("、"),
        subtasks_text: (item.subtasks || []).join("、"),
      };
    };
    const newEditor = () => { editor.value = { name: "", owner: "", priority: "normal", status: "待处理", description: "", due_date: "", tags_text: "", subtasks_text: "", comment_draft: "" }; };
    const clearFilters = async () => { search.value = ""; priority.value = "all"; assignee.value = "all"; await loadItems(1); };
    const save = async () => {
      const method = editor.value.id ? "PUT" : "POST";
      const path = editor.value.id ? `/api/arena/items/${editor.value.id}` : "/api/arena/items";
      const payload = { ...editor.value, tags: editor.value.tags_text.split("、").map((value) => value.trim()).filter(Boolean), subtasks: editor.value.subtasks_text.split("、").map((value) => value.trim()).filter(Boolean) };
      delete payload.tags_text; delete payload.subtasks_text;
      try {
        const saved = await request(path, { method, body: JSON.stringify(payload) }); editor.value = null;
        active.value = saved; notice.value = "保存成功，协作信息已更新。"; await Promise.all([loadItems(1), loadSummary()]);
      } catch (caught) { error.value = caught.message; }
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
      confirmation.value = null; selected.value = []; undoAvailable.value = true; notice.value = "已删除，可立即撤销。";
      await Promise.all([loadItems(), loadSummary()]);
    };
    const undo = async () => { try { const result = await request("/api/arena/undo", { method: "POST" }); undoAvailable.value = false; notice.value = `已恢复 ${result.restored} 条任务`; await Promise.all([loadItems(), loadSummary()]); } catch (caught) { error.value = caught.message; } };
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
    watch(section, () => { active.value = null; notice.value = ""; error.value = ""; });
    onMounted(async () => {
      window.addEventListener("keydown", onKeydown);
      await Promise.all([loadItems(1), loadSummary(), pollProgress()]); progressTimer = window.setInterval(pollProgress, 2000);
    });
    onUnmounted(() => { window.removeEventListener("keydown", onKeydown); if (progressTimer) window.clearInterval(progressTimer); });
    return { sections, section, title, state, summary, progress, selected, search, priority, assignee, sort, active, editor, confirmation, notice, projectDetail, loading, error, undoAvailable, pageCount, navigate, loadItems, start, interrupt, openItem, openProject, openProjectTask, openEditor, newEditor, clearFilters, save, batch, confirm, undo, toggleAutomation, updateSettings };
  },
  template: `
    <main class="shell">
      <aside class="nav"><h1>星轨协作</h1><p>本地 GUI Agent 评测场</p>
        <button v-for="entry in sections" :key="entry[0]" :class="{active: section===entry[0]}" @click="navigate(entry[0])">{{ entry[1] }}</button>
        <footer>离线环境 · 数据可重置</footer>
      </aside>
      <section class="workspace">
        <header><div><span class="eyebrow">星轨协作 / {{ title }}</span><h2>{{ title }}</h2><p>通过可见界面完成项目协作工作。</p></div><span v-if="notice" class="notice">{{ notice }}</span></header>
        <p v-if="error" class="feedback error" role="alert">{{ error }}</p>
        <template v-if="section==='home'">
          <section class="hero"><div><span class="eyebrow">今日概览</span><h3>让团队工作保持清晰</h3><p>从左侧导航进入各业务模块，处理任务、项目和自动化流程。</p></div><div class="date-card">8 月 26 日<br><b>星期三</b></div></section>
          <section class="stats"><article v-for="(value,key) in summary.counts" :key="key"><span>{{ key }}</span><strong>{{ value }}</strong></article></section>
          <section class="panel"><div class="section-title"><div><h3>评测运行</h3><p>选择固定冒烟集或完整任务集。</p></div><span>状态：{{ progress.status }}　{{ progress.completed }}/{{ progress.total || '未选择' }}</span></div><div class="actions"><button class="primary" :disabled="progress.status==='running'||progress.status==='interrupting'" @click="start(10)">运行 10 条</button><button :disabled="progress.status==='running'||progress.status==='interrupting'" @click="start(100)">运行 100 条</button><button v-if="progress.status==='running'||progress.status==='interrupting'" class="danger" @click="interrupt">中断（Esc）</button></div></section>
          <section class="grid-two"><article class="panel"><h3>重点项目</h3><button v-for="project in summary.projects.slice(0,3)" :key="project.name" class="project-row" @click="openProject(project)"><span><b>{{ project.name }}</b><small>{{ project.owner }} 负责 · {{ project.overdue }} 项逾期</small></span><strong>{{ project.progress }}%</strong></button></article><article class="panel"><h3>协作动态</h3><div v-for="event in summary.activity.slice(0,3)" :key="event.time+event.detail" class="event-row"><span>{{ event.kind }}</span><b>{{ event.detail }}</b></div></article></section>
        </template>
        <template v-else-if="section==='inbox'"><section class="panel inbox-list"><button v-for="item in state.items.slice(0,5)" :key="item.id" @click="openItem(item)"><span class="dot" :class="item.priority"></span><span><b>{{ item.name }}</b><small>{{ item.owner }} · {{ item.status }}</small></span><time>{{ item.updated_at }}</time></button></section></template>
        <template v-else-if="section==='projects'"><section class="card-grid"><article v-for="project in summary.projects" :key="project.name" class="project-card"><div class="project-icon">{{ project.name.slice(0,1) }}</div><h3>{{ project.name }}</h3><p>{{ project.owner }} 负责 · {{ project.overdue }} 项逾期 · {{ project.task_count }} 项任务</p><div class="progress"><i :style="{width:project.progress+'%'}"></i></div><strong>{{ project.progress }}%</strong><button @click="openProject(project)">查看项目详情</button></article></section></template>
        <template v-else-if="section==='tasks'">
          <section class="filters"><input v-model="search" @keyup.enter="loadItems(1)" placeholder="搜索任务名称或负责人" /><select v-model="priority"><option value="all">全部优先级</option><option value="high">高</option><option value="normal">普通</option><option value="low">低</option></select><select v-model="assignee"><option value="all">全部负责人</option><option v-for="member in summary.members" :key="member.name" :value="member.name">{{ member.name }}</option></select><select v-model="sort"><option value="updated_desc">最近更新</option><option value="name">名称</option></select><button @click="loadItems(1)">筛选</button><button v-if="state.has_filters" @click="clearFilters">清除筛选</button><button class="primary" @click="newEditor">新建任务</button></section>
          <section class="toolbar"><span>已选择 {{ selected.length }} 项</span><button :disabled="!selected.length" @click="batch('priority')">设为高优先级</button><button :disabled="!selected.length" @click="batch('complete')">标为完成</button><button :disabled="!selected.length" class="danger" @click="batch('delete')">删除</button><button v-if="undoAvailable" @click="undo">撤销删除</button></section>
          <p v-if="loading" class="feedback">正在加载任务…</p><section v-else-if="!state.items.length" class="empty-state"><h3>没有匹配任务</h3><p>调整筛选条件，或清除筛选后查看全部任务。</p><button v-if="state.has_filters" @click="clearFilters">清除筛选</button></section><table v-else><thead><tr><th></th><th>任务名称</th><th>负责人</th><th>状态</th><th>优先级</th><th>更新时间</th></tr></thead><tbody><tr v-for="item in state.items" :key="item.id"><td><input type="checkbox" :value="item.id" v-model="selected" /></td><td><button class="link" @click="openItem(item)">{{ item.name }}</button></td><td>{{ item.owner }}</td><td><span class="tag">{{ item.status }}</span></td><td>{{ item.priority }}</td><td>{{ item.updated_at }}</td></tr></tbody></table>
          <footer class="pager"><span>共 {{ state.total }} 条</span><button :disabled="state.page===1" @click="loadItems(state.page-1)">上一页</button><span>{{ state.page }} / {{ pageCount }}</span><button :disabled="state.page===pageCount" @click="loadItems(state.page+1)">下一页</button></footer>
        </template>
        <template v-else-if="section==='calendar'"><section class="calendar"><article v-for="event in summary.events" :key="event.title"><span>{{ event.date }}</span><div><small>{{ event.kind }}</small><h3>{{ event.title }}</h3></div></article></section></template>
        <template v-else-if="section==='automation'"><section class="panel rule-list"><article v-for="rule in summary.automations" :key="rule.id"><div><h3>{{ rule.name }}</h3><p>满足条件时自动执行，无需离开当前工作区。</p></div><button :class="{primary:rule.enabled}" @click="toggleAutomation(rule)">{{ rule.enabled ? '已启用' : '启用' }}</button></article></section></template>
        <template v-else-if="section==='team'"><section class="card-grid"><article v-for="member in summary.members" :key="member.name" class="member-card"><div class="avatar">{{ member.name.slice(0,1) }}</div><h3>{{ member.name }}</h3><p>{{ member.role }}</p><span>{{ member.workload }}</span></article></section></template>
        <template v-else-if="section==='reports'"><section class="stats report-stats"><article v-for="metric in summary.metrics" :key="metric.label" tabindex="0"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong><small>{{ metric.detail }}</small></article></section><section class="panel chart"><h3>最近六周完成趋势</h3><div class="bars"><i v-for="height in [42,58,49,72,66,84]" :key="height" :style="{height:height+'%'}"></i></div></section></template>
        <template v-else-if="section==='settings'"><section class="panel settings"><h3>外观</h3><label>主题<select :value="summary.settings.theme" @change="updateSettings({theme:$event.target.value})"><option>浅色</option><option>深色</option></select></label><label class="switch-row"><span><b>紧凑布局</b><small>在列表中显示更多内容</small></span><input type="checkbox" :checked="summary.settings.compact" @change="updateSettings({compact:$event.target.checked})" /></label></section></template>
      </section>
      <aside v-if="projectDetail || active" class="detail"><div class="section-title"><h3>详情</h3><button class="link" @click="projectDetail=null;active=null">关闭</button></div><template v-if="projectDetail"><p><b>{{ projectDetail.name }}</b></p><dl><dt>负责人</dt><dd>{{ projectDetail.owner }}</dd><dt>风险任务</dt><dd>{{ projectDetail.risk_task }}</dd><dt>里程碑</dt><dd>{{ projectDetail.milestones.join(' · ') }}</dd><dt>成员负载</dt><dd v-for="member in projectDetail.members" :key="member.name">{{ member.name }}：{{ member.workload }} 项</dd></dl><h3>关联任务</h3><button v-for="item in projectDetail.tasks" :key="item.id" class="project-row" @click="openProjectTask(item)">{{ item.name }}<small>{{ item.status }} · {{ item.owner }}</small></button></template><template v-else><p><b>{{ active.name }}</b></p><dl><dt>项目</dt><dd>{{ active.project }}</dd><dt>负责人</dt><dd>{{ active.owner }}</dd><dt>状态</dt><dd>{{ active.status }}</dd><dt>截止日期</dt><dd>{{ active.due_date }}</dd><dt>标签</dt><dd>{{ active.tags.join(' · ') }}</dd><dt>子任务</dt><dd>{{ active.subtasks.join(' · ') }}</dd><dt>评论草稿</dt><dd>{{ active.comment_draft || '暂无草稿' }}</dd><dt>描述</dt><dd>{{ active.description }}</dd></dl><button class="primary" @click="openEditor(active)">编辑任务</button></template></aside>
      <div v-if="editor" class="modal"><form @submit.prevent="save"><h3>{{ editor.id ? '编辑任务' : '新建任务' }}</h3><label>名称<input v-model="editor.name" /></label><label>负责人<select v-model="editor.owner"><option value="">请选择</option><option v-for="member in summary.members" :key="member.name">{{ member.name }}</option></select></label><label>优先级<select v-model="editor.priority"><option value="high">高</option><option value="normal">普通</option><option value="low">低</option></select></label><label>状态<select v-model="editor.status"><option>待处理</option><option>进行中</option><option>已完成</option><option>已逾期</option></select></label><label>截止日期<input v-model="editor.due_date" type="date" /></label><label>标签（用顿号分隔）<input v-model="editor.tags_text" placeholder="风险、已核验" /></label><label>子任务（用顿号分隔）<input v-model="editor.subtasks_text" placeholder="复核、通知" /></label><label>评论草稿<textarea v-model="editor.comment_draft"></textarea></label><label>描述<textarea v-model="editor.description"></textarea></label><div><button type="button" @click="editor=null">取消</button><button class="primary" type="submit">保存</button></div></form></div>
      <div v-if="confirmation" class="modal"><section class="confirm"><h3>{{ confirmation.title }}</h3><p>{{ confirmation.content }}</p><div><button @click="confirmation=null">取消</button><button class="danger" @click="confirm">确认删除</button></div></section></div>
    </main>`,
};

createApp(App).use(router).mount("#app");

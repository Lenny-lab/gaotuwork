const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const $ = id => document.getElementById(id);
const page = document.body.dataset.page;
let plansPayload;
let demoData;

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`);
  return data;
}

function updateMetrics(plan) {
  const score = plan.scorecard;
  if ($('score')) $('score').textContent = score.overall_score;
  if ($('lessons')) $('lessons').textContent = plan.metrics.lesson_count;
  if ($('conflicts')) $('conflicts').textContent = score.hard_conflicts;
  if ($('teacher-rate')) $('teacher-rate').textContent = `${score.teacher_preference_rate}%`;
  if ($('capacity-rate')) $('capacity-rate').textContent = `${score.capacity_fit_rate}%`;
}

function planButtons(plans) {
  return plans.map(plan => `<button class="plan" data-id="${plan.id}"><span class="plan-head"><b>${plan.name}</b><em>${plan.scorecard.overall_score}</em></span><span class="plan-copy">学生 ${plan.scorecard.student_preference_rate}% · 教师 ${plan.scorecard.teacher_preference_rate}% · 容量 ${plan.scorecard.capacity_fit_rate}%</span></button>`).join('');
}

function renderPlan(plan) {
  updateMetrics(plan);
  if ($('legend')) $('legend').textContent = `${plan.name} · ${plan.status}`;
  if ($('schedule')) {
    const grouped = plan.schedule.reduce((result, item) => {
      (result[item.day] ??= []).push(item);
      return result;
    }, {});
    $('schedule').innerHTML = days.map(day => `<div class="day"><strong>${day}</strong>${(grouped[day] || []).map(item => `<div class="lesson"><b>${item.course_name}</b><span>${item.period}</span><span>${item.teacher_name} · ${item.room_name}</span></div>`).join('')}</div>`).join('');
  }
  if ($('calendar')) renderCalendar(plan.schedule);
  document.querySelectorAll('.plan').forEach(item => item.classList.toggle('selected', item.dataset.id === plan.id));
}

function minutes(value) {
  const [hour, minute] = value.split(':').map(Number);
  return hour * 60 + minute;
}

function renderCalendar(schedule) {
  const startMinute = 8 * 60;
  const endMinute = 17 * 60 + 30;
  const total = endMinute - startMinute;
  const workDays = days.slice(0, 5);
  const labels = ['08:00','09:00','10:00','11:00','12:00','13:30','14:30','15:30','16:30','17:30'];
  const byDay = schedule.reduce((result, item) => ((result[item.day] ??= []).push(item), result), {});
  const timeAxis = labels.map(label => {
    const top = (minutes(label) - startMinute) / total * 100;
    return `<span style="top:${top}%">${label}</span>`;
  }).join('');
  const columns = workDays.map(day => {
    const events = (byDay[day] || []).map(item => {
      const [start, end] = item.period.split('-');
      const top = (minutes(start) - startMinute) / total * 100;
      const height = (minutes(end) - minutes(start)) / total * 100;
      return `<div class="calendar-event" style="top:${top}%;height:${height}%"><b>${item.course_name}</b><span>${item.period}</span><small>${item.teacher_name} · ${item.room_name}</small></div>`;
    }).join('');
    return `<div class="calendar-day"><div class="lunch-band"><span>午休</span></div>${events}</div>`;
  }).join('');
  $('calendar').innerHTML = `<div class="calendar-scroll" aria-label="可横向滚动的周课表"><div class="calendar-head"><div>时间</div>${workDays.map(day => `<strong>${day}</strong>`).join('')}</div><div class="calendar-body"><div class="time-axis">${timeAxis}</div><div class="calendar-days">${columns}</div></div></div>`;
}

function dashboardSummary(plan) {
  const lessonsByDay = plan.schedule.reduce((result, item) => ((result[item.day] = (result[item.day] || 0) + 1), result), {});
  const busiest = Object.entries(lessonsByDay).sort((a, b) => b[1] - a[1])[0];
  $('decision-summary').innerHTML = `<div class="summary-status"><i></i><div><b>当前课表可发布</b><span>${plan.metrics.lesson_count} 个课次全部满足硬约束</span></div></div><div class="summary-list"><div><span>本周高峰</span><b>${busiest[0]} · ${busiest[1]} 课次</b></div><div><span>参与教师</span><b>${plan.metrics.teacher_count} 人</b></div><div><span>使用教室</span><b>${plan.metrics.room_count} 间</b></div><div><span>求解耗时</span><b>${plan.metrics.solve_time_ms} ms</b></div></div><div class="quick-actions"><a href="/schedule.html">比较排课方案</a><a href="/reschedule.html">处理临时请假</a></div>`;
}

function explainBreakdown(plan) {
  const score = plan.scorecard;
  const rows = [
    {label: '学生偏好未命中', value: score.soft_objective.student_miss, hint: '若全部命中，0 个偏差'},
    {label: '教师偏好未命中', value: score.soft_objective.teacher_miss, hint: '可在数据中放宽 preferred_slots 改善'},
    {label: '教师日均方差', value: score.stability_variance.toFixed(2), hint: '数值越低，老师课表越均匀'},
  ];
  return `<div class="explain-rows">${rows.map(item => `<div><span>${item.label}</span><b>${item.value}</b><small>${item.hint}</small></div>`).join('')}</div><div class="explain-foot"><i></i><b>原始目标值</b><span>CP-SAT 最小化的目标 = ${plan.metrics.objective_value}</span></div>`;
}

async function loadPlans() {
  try {
    plansPayload = await api('/api/plans');
    if ($('plans')) {
      $('plans').innerHTML = planButtons(plansPayload.plans);
      document.querySelectorAll('.plan').forEach(element => {       element.onclick = () => {
        const plan = plansPayload.plans.find(item => item.id === element.dataset.id);
        renderPlan(plan);
        if (page === 'dashboard') {
          dashboardSummary(plan);
          $('explain-grid').innerHTML = explainBreakdown(plan);
        }
      }; });
    }
    renderPlan(plansPayload.plans[0]);
    if (page === 'dashboard') {
      dashboardSummary(plansPayload.plans[0]);
      $('explain-grid').innerHTML = explainBreakdown(plansPayload.plans[0]);
    }
  } catch (error) {
    if ($('legend')) $('legend').textContent = `服务连接失败：${error.message}`;
    if ($('decision-summary')) $('decision-summary').innerHTML = `<div class="error-state"><b>数据加载失败</b><span>${error.message}</span></div>`;
  }
}

async function loadAdminStatistics() {
  if (!$('admin-statistics')) return;
  try {
    const data = await api('/api/admin/statistics');
    const items = [
      ['业务账号', data.users.total, `学生 ${data.users.students} · 教师 ${data.users.teachers} · 教务 ${data.users.academic_affairs}`, ''],
      ['飞书已绑定', data.users.bound, `待绑定 ${data.users.pending} 个`, data.users.pending ? 'stat-warn' : 'stat-good'],
      ['教学资源', data.resources.teachers + data.resources.rooms, `教师 ${data.resources.teachers} · 教室 ${data.resources.rooms}`, ''],
      ['班级学生', data.resources.students, `${data.resources.classes} 个班级`, ''],
      ['课程门数', data.resources.courses, `需求 ${data.resources.requested_lessons} 课次`, ''],
      ['已排课次', data.schedule.scheduled_lessons, `求解状态 ${data.schedule.status}`, 'stat-good'],
      ['硬冲突', data.schedule.hard_conflicts, '全局独立校验结果', data.schedule.hard_conflicts ? 'stat-warn' : 'stat-good'],
      ['数据范围', '全局', '教务专属统计权限', 'stat-good'],
    ];
    $('admin-statistics').innerHTML = items.map(item => `<article class="${item[3]}"><span>${item[0]}</span><b>${item[1]}</b><small>${item[2]}</small></article>`).join('');
  } catch (error) {
    $('admin-statistics').innerHTML = `<div class="error-state"><b>全局统计加载失败</b><span>${error.message}</span></div>`;
  }
}

async function loadDemo() {
  demoData = await api('/api/demo');
  return demoData;
}

async function setupReschedule() {
  try {
    const demo = await loadDemo();
    $('leave-teacher').innerHTML = demo.teachers.map(item => `<option value="${item.id}">${item.name} · ${item.qualifications.join('/')}</option>`).join('');
    $('leave-slot').innerHTML = demo.time_slots.map(item => `<option value="${item.id}">${item.day} ${item.period}</option>`).join('');
    $('leave-teacher').disabled = false;
    $('leave-slot').disabled = false;
    $('simulate').disabled = false;
    $('simulate').textContent = '生成最小影响方案';
  } catch (error) {
    $('impact').innerHTML = `<div class="error-state"><b>基础数据加载失败</b><span>${error.message}</span></div>`;
  }
}

async function simulate() {
  const button = $('simulate');
  if (!$('leave-teacher').value || !$('leave-slot').value) return;
  button.disabled = true;
  button.textContent = '正在局部重排…';
  $('impact').innerHTML = '<div class="empty-state"><b>CP-SAT 正在计算</b><span>锁定未受影响课程并寻找最少变更方案。</span></div>';
  try {
    const data = await api('/api/reschedule', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({teacher_id: $('leave-teacher').value, slot_id: $('leave-slot').value})});
    const rows = data.diff.changes.map(item => `<div><strong>${item.after?.course_name || item.before?.course_name}</strong><span>${item.before ? item.before.day + ' ' + item.before.period : '未安排'} → ${item.after ? item.after.day + ' ' + item.after.period : '取消'}</span><small>${item.before?.teacher_name || '—'} → ${item.after?.teacher_name || '—'} · ${item.after?.room_name || '—'}</small></div>`).join('');
    $('impact').innerHTML = `<div class="impact-top"><div><span>变更课次</span><b>${data.impact.changed_lessons}</b></div><div><span>影响班级</span><b>${data.impact.affected_class_count}</b></div><div><span>硬冲突</span><b>${data.after.conflicts.length}</b></div></div><div class="change-list">${rows || '<p>所选时段没有该教师课程，无需调整。</p>'}</div>`;
  } catch (error) {
    $('impact').innerHTML = `<div class="error-state"><b>重排失败</b><span>${error.message}</span></div>`;
  } finally {
    button.disabled = false;
    button.textContent = '生成最小影响方案';
  }
}

const resourceConfig = {
  teachers: {title: '教师资源', headers: ['教师', '学科资质', '偏好时段', '不可用时段'], rows: item => [item.name, item.qualifications.join('、'), item.preferred_slots?.join('、') || '—', item.unavailable?.join('、') || '—']},
  rooms: {title: '教室资源', headers: ['教室', '校区', '容量', '设备'], rows: item => [item.name, item.campus, `${item.capacity} 人`, item.equipment.join('、')]},
  classes: {title: '班级资源', headers: ['班级', '人数', '偏好时段', '不可用时段'], rows: item => [item.name, `${item.size} 人`, item.preferred_slots?.join('、') || '—', item.unavailable?.join('、') || '—']},
  courses: {title: '课程需求', headers: ['课程', '学科', '班级', '课次', '设备要求'], rows: item => [item.name, item.subject, item.class_id, `${item.sessions} 次`, item.required_equipment?.join('、') || '无']},
};

function renderResources(type) {
  const config = resourceConfig[type];
  const items = demoData[type];
  $('resource-title').textContent = config.title;
  $('resource-count').textContent = `共 ${items.length} 条`;
  $('resource-head').innerHTML = `<tr>${config.headers.map(item => `<th>${item}</th>`).join('')}</tr>`;
  $('resource-body').innerHTML = items.map(item => `<tr>${config.rows(item).map(cell => `<td>${cell}</td>`).join('')}</tr>`).join('');
  document.querySelectorAll('.resource-tabs button').forEach(button => button.classList.toggle('active', button.dataset.resource === type));
}

async function setupResources() {
  try {
    const demo = await loadDemo();
    const cards = [['教师', demo.teachers.length, `覆盖 ${new Set(demo.teachers.flatMap(item => item.qualifications)).size} 个学科`], ['教室', demo.rooms.length, `总容量 ${demo.rooms.reduce((sum, item) => sum + item.capacity, 0)} 人`], ['班级', demo.classes.length, `学生 ${demo.classes.reduce((sum, item) => sum + item.size, 0)} 人`], ['课程', demo.courses.length, `共 ${demo.courses.reduce((sum, item) => sum + item.sessions, 0)} 个课次`]];
    $('resource-cards').innerHTML = cards.map(item => `<div><span>${item[0]}</span><b>${item[1]}</b><small>${item[2]}</small></div>`).join('');
    document.querySelectorAll('.resource-tabs button').forEach(button => { button.onclick = () => renderResources(button.dataset.resource); });
    renderResources('teachers');
  } catch (error) {
    $('resource-body').innerHTML = `<tr><td>资源数据加载失败：${error.message}</td></tr>`;
  }
}

if (page === 'dashboard' || page === 'schedule') {
  $('refresh').onclick = loadPlans;
  loadPlans();
  if (page === 'dashboard') loadAdminStatistics();
} else if (page === 'reschedule') {
  $('simulate').onclick = simulate;
  setupReschedule();
} else if (page === 'resources') {
  setupResources();
}

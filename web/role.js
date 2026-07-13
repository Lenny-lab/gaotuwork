const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
})[char]);

async function api(url, options) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `请求失败 ${response.status}`);
  return data;
}

function lessonRows(items) {
  if (!items.length) return '<div class="empty">当前没有安排</div>';
  return `<div class="lesson-list">${items.map(item => `<div class="lesson"><div class="lesson-time">${esc(item.day)}<span>${esc(item.period)}</span></div><div><strong>${esc(item.course_name)}</strong><span>${esc(item.class_name)} · ${esc(item.teacher_name)}</span></div><div><strong>${esc(item.room_name)}</strong><span>${esc(item.slot_id)}</span></div></div>`).join('')}</div>`;
}

const calendarDays = ['周一', '周二', '周三', '周四', '周五'];

function timeMinutes(value) {
  const [hour, minute] = value.split(':').map(Number);
  return hour * 60 + minute;
}

function currentWeekDates() {
  const today = new Date();
  const day = today.getDay() || 7;
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - day + 1);
  return calendarDays.map((_, index) => {
    const date = new Date(monday);
    date.setDate(monday.getDate() + index);
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  });
}

function weekCalendar(items) {
  const start = timeMinutes('08:00');
  const end = timeMinutes('17:30');
  const total = end - start;
  const dates = currentWeekDates();
  const labels = ['08:00', '09:00', '10:00', '11:00', '12:00', '13:30', '14:30', '15:30', '16:30', '17:30'];
  const byDay = items.reduce((result, item) => {
    (result[item.day] ??= []).push(item);
    return result;
  }, {});
  const timeAxis = labels.map(label => {
    const top = (timeMinutes(label) - start) / total * 100;
    return `<span style="top:${top}%">${label}</span>`;
  }).join('');
  const columns = calendarDays.map(day => {
    const events = (byDay[day] || []).map(item => {
      const [eventStart, eventEnd] = item.period.split('-');
      const top = (timeMinutes(eventStart) - start) / total * 100;
      const height = (timeMinutes(eventEnd) - timeMinutes(eventStart)) / total * 100;
      return `<article class="week-event" style="top:${top}%;height:${height}%"><strong>${esc(item.course_name)}</strong><span>${esc(item.period)}</span><small>${esc(item.class_name)} · ${esc(item.teacher_name)}</small><small>${esc(item.room_name)}</small></article>`;
    }).join('');
    return `<div class="week-day"><div class="week-lunch"><strong>午休</strong><span>12:00–13:30</span></div>${events}</div>`;
  }).join('');
  return `<div class="week-calendar-card"><div class="calendar-meta"><div><strong>本周日程</strong><span>08:00–17:30 · 午休已标记</span></div><span class="calendar-zone">北京时间</span></div><div class="week-calendar-scroll" aria-label="包含日期和时间轴的周日历"><div class="week-calendar-head"><div class="week-corner">时间</div>${calendarDays.map((day, index) => `<div><strong>${day}</strong><span>${dates[index]}</span></div>`).join('')}</div><div class="week-calendar-body"><div class="week-time-axis">${timeAxis}</div><div class="week-days">${columns}</div></div></div></div>`;
}

function setIdentity(me) {
  $$('[data-user-name]').forEach(node => { node.textContent = me.name; });
  $$('[data-user-role]').forEach(node => { node.textContent = ({ student: '学生', teacher: '教师', academic_affairs: '教务' })[me.role] || me.role; });
}

function setMetric(selector, value) {
  const node = $(selector);
  node.textContent = value;
  node.classList.remove('skeleton');
}

function businessScope(user) {
  if (user.role === 'student') return `班级 ${user.class_id || '待配置'}`;
  if (user.role === 'teacher') return `教师 ${user.teacher_id || '待配置'}`;
  return '全局教务';
}

function renderAdminUsers(users) {
  const roleLabel = { student: '学生', teacher: '教师', academic_affairs: '教务' };
  $('#content').innerHTML = `<div class="table-wrap"><table><thead><tr><th>姓名</th><th>角色</th><th>业务映射</th><th>飞书 Open ID</th><th>状态</th></tr></thead><tbody>${users.map(user => `<tr><td><strong>${esc(user.name)}</strong><br><span class="label">${esc(user.id)}</span></td><td><span class="pill">${esc(roleLabel[user.role])}</span></td><td>${esc(businessScope(user))}</td><td>${esc(user.open_id || '待绑定')}</td><td class="${user.open_id ? 'status-bound' : 'status-pending'}">${user.open_id ? '已绑定' : '待回填真实 ID'}</td></tr>`).join('')}</tbody></table></div>`;
  const select = $('#binding-user');
  const current = select.value;
  select.innerHTML = '<option value="">请选择业务用户</option>' + users.map(user => `<option value="${esc(user.id)}">${esc(user.name)} · ${esc(roleLabel[user.role])} · ${esc(businessScope(user))}${user.open_id ? ' · 已绑定' : ''}</option>`).join('');
  if (users.some(user => user.id === current)) select.value = current;
}

async function setupAdminBindings() {
  let payload = await api('/api/admin/users');
  renderAdminUsers(payload.users);
  $('#binding-form').addEventListener('submit', async event => {
    event.preventDefault();
    const button = event.currentTarget.querySelector('button');
    const notice = $('#binding-notice');
    button.disabled = true;
    notice.style.display = 'none';
    try {
      const result = await api('/api/admin/users/bind-by-mobile', {
        method: 'POST',
        body: JSON.stringify({ user_id: $('#binding-user').value, mobile: $('#binding-mobile').value }),
      });
      notice.className = 'notice';
      notice.textContent = result.message;
      notice.style.display = 'block';
      $('#binding-mobile').value = '';
      payload = await api('/api/admin/users');
      renderAdminUsers(payload.users);
    } catch (error) {
      notice.className = 'notice error';
      notice.textContent = error.message;
      notice.style.display = 'block';
    } finally {
      button.disabled = false;
    }
  });
}

async function start() {
  try {
    const me = await api('/api/me');
    setIdentity(me);
    const view = document.body.dataset.view;
    if (view === 'student-dashboard') {
      const [schedule, exams] = await Promise.all([api('/api/student/me/schedule'), api('/api/student/me/exams')]);
      setMetric('#metric-grade', me.grade || '高一');
      $('#metric-age').textContent = me.age || 16;
      setMetric('#metric-lessons', schedule.schedule.length);
      setMetric('#metric-days', new Set(schedule.schedule.map(item => item.day)).size);
      setMetric('#metric-exams', exams.exams.length);
      $('#content').className = '';
      $('#content').innerHTML = weekCalendar(schedule.schedule);
    }
    if (view === 'student-schedule') {
      const schedule = await api('/api/student/me/schedule');
      $('#content').className = '';
      $('#content').innerHTML = weekCalendar(schedule.schedule);
    }
    if (view === 'student-exams') {
      const payload = await api('/api/student/me/exams');
      $('#content').innerHTML = payload.exams.length ? `<div class="table-wrap"><table><thead><tr><th>课程</th><th>测评类型</th><th>日期</th><th>时间</th><th>地点</th></tr></thead><tbody>${payload.exams.map(item => `<tr><td><strong>${esc(item.course_name)}</strong></td><td>${esc(item.type)}</td><td>${esc(item.day)}</td><td>${esc(item.period)}</td><td>${esc(item.room_name)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">暂无考试安排</div>';
    }
    if (view === 'teacher-dashboard') {
      const [schedule, workload, students] = await Promise.all([api('/api/teacher/me/schedule'), api('/api/teacher/me/workload'), api('/api/teacher/me/students')]);
      setMetric('#metric-teaching-grades', (me.teaching_grades || ['高一', '初三']).join(' / '));
      $('#metric-experience').textContent = me.years_experience || 6;
      setMetric('#metric-lessons', workload.lesson_count);
      setMetric('#metric-classes', workload.class_count);
      setMetric('#metric-students', students.students.length);
      $('#content').className = '';
      $('#content').innerHTML = weekCalendar(schedule.schedule);
    }
    if (view === 'teacher-schedule') {
      const schedule = await api('/api/teacher/me/schedule');
      $('#content').className = '';
      $('#content').innerHTML = weekCalendar(schedule.schedule);
    }
    if (view === 'teacher-leave') {
      const schedule = await api('/api/teacher/me/schedule');
      const select = $('#slot');
      select.innerHTML = '<option value="">请选择要请假的课程</option>' + schedule.schedule.map(item => `<option value="${esc(item.slot_id)}">${esc(item.day)} ${esc(item.period)} · ${esc(item.course_name)}</option>`).join('');
      $('#leave-form').addEventListener('submit', async event => {
        event.preventDefault();
        const button = $('.btn');
        const notice = $('#notice');
        button.disabled = true;
        try {
          const output = await api('/api/teacher/leave', { method: 'POST', body: JSON.stringify({ slot_id: select.value, reason: $('#reason').value }) });
          notice.className = 'notice';
          notice.textContent = `模拟申请已生成：影响 ${output.impact.changed_lessons} 节课、${output.impact.affected_class_count} 个班级。`;
          notice.style.display = 'block';
        } catch (error) {
          notice.className = 'notice error';
          notice.textContent = error.message;
          notice.style.display = 'block';
        } finally {
          button.disabled = false;
        }
      });
    }
    if (view === 'admin-users') await setupAdminBindings();
  } catch (error) {
    const content = $('#content');
    if (content) content.innerHTML = `<div class="notice error" style="display:block">${esc(error.message)}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', start);

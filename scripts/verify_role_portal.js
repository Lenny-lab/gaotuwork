const { chromium } = require('../tmp/browserdeps/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', error => errors.push(error.message));

  await page.goto('http://127.0.0.1:5099/', { waitUntil: 'networkidle' });
  const heading = await page.locator('h1').innerText();
  const roles = await page.locator('.role').count();
  if (!heading.includes('请选择你的 ClassMind 工作台') || roles !== 3) {
    throw new Error(`portal mismatch: heading=${heading}, roles=${roles}`);
  }
  await page.screenshot({ path: 'tmp/role-portal-mobile.png', fullPage: true });

  await page.getByText('体验学生工作台').click();
  await page.waitForURL('**/student/dashboard');
  await page.waitForFunction(() => document.body.innerText.includes('朱晴晴') && !document.querySelector('#metric-grade')?.classList.contains('skeleton'));
  const studentText = await page.locator('body').innerText();
  if (!studentText.includes('朱晴晴') || !studentText.includes('高一') || !studentText.includes('本周课程日历') || !studentText.includes('12:00–13:30') || !studentText.includes('7月')) throw new Error('student profile or dated calendar missing');
  await page.screenshot({ path: 'tmp/student-dashboard-mobile.png', fullPage: true });

  await page.goto('http://127.0.0.1:5099/', { waitUntil: 'networkidle' });
  if (await page.locator('.role').count() !== 3) throw new Error('portal hidden by student session');
  await page.getByText('体验教师工作台').click();
  await page.waitForURL('**/teacher/dashboard');
  await page.waitForFunction(() => document.body.innerText.includes('张锦倪') && !document.querySelector('#metric-teaching-grades')?.classList.contains('skeleton'));
  const teacherText = await page.locator('body').innerText();
  if (!teacherText.includes('张锦倪') || !teacherText.includes('高一 / 初三') || !teacherText.includes('本周授课日历') || !teacherText.includes('12:00–13:30') || !teacherText.includes('7月')) throw new Error('teacher profile or dated calendar missing');
  await page.screenshot({ path: 'tmp/teacher-dashboard-mobile.png', fullPage: true });
  const calendar = page.locator('.week-calendar-scroll');
  const scrollState = await calendar.evaluate(element => {
    element.scrollLeft = element.scrollWidth;
    return { left: element.scrollLeft, max: element.scrollWidth - element.clientWidth };
  });
  if (scrollState.left <= 0 || scrollState.max <= 0) throw new Error('calendar horizontal scrolling unavailable');
  await page.screenshot({ path: 'tmp/teacher-dashboard-calendar-friday.png', fullPage: true });

  await page.goto('http://127.0.0.1:5099/', { waitUntil: 'networkidle' });
  await page.getByText('体验教务工作台').click();
  await page.waitForURL('**/admin/dashboard');
  if (!(await page.locator('body').innerText()).includes('早上好，教务老师')) throw new Error('admin dashboard missing');
  if (await page.locator('a[href="/portal"]').count() < 1) throw new Error('admin portal return link missing');
  await page.waitForFunction(() => document.body.innerText.includes('最高统计权限') && !document.querySelector('#admin-statistics')?.innerText.includes('正在汇总'));
  if (!(await page.locator('#admin-statistics').innerText()).includes('数据范围')) throw new Error('admin global statistics missing');
  await page.screenshot({ path: 'tmp/admin-global-statistics-mobile.png', fullPage: true });

  await page.goto('http://127.0.0.1:5099/admin/users', { waitUntil: 'networkidle' });
  const adminText = await page.locator('body').innerText();
  if (!adminText.includes('通过手机号绑定飞书账号') || !adminText.includes('朱晴晴') || !adminText.includes('张锦倪')) throw new Error('admin mobile binding UI missing');
  await page.screenshot({ path: 'tmp/admin-mobile-binding.png', fullPage: true });

  console.log(JSON.stringify({ heading, roles, finalUrl: page.url(), studentProfile: true, teacherProfile: true, datedWeekCalendar: true, synchronizedCalendarScroll: scrollState, adminGlobalStatistics: true, mobileBindingUI: true, consoleErrors: errors }, null, 2));
  await browser.close();
  if (errors.length) process.exitCode = 1;
})().catch(error => {
  console.error(error);
  process.exit(1);
});

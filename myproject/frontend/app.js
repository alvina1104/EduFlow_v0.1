
(function(){
"use strict";
var app=document.getElementById("app");
var COLORS=["violet","blue","cyan","green","orange","pink"];
var state={token:null,refresh:null,user:null,students:[],groups:[],contracts:[],payments:[],profile:null,study:null,balances:[],loadError:null,view:"dashboard",selected:null,photoUrl:null,ready:false,loading:false};
var pref={theme:localStorage.getItem("eduflow.theme")==="light"?"light":"dark",accent:COLORS.includes(localStorage.getItem("eduflow.accent"))?localStorage.getItem("eduflow.accent"):"violet"};
function el(id){return document.getElementById(id)}
function ico(name){return '<svg aria-hidden="true"><use href="#i-'+name+'"></use></svg>'}
function escapeHtml(t){return String(t==null?"":t).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function safe(t){return escapeHtml(t)}
function text(t,fallback){return t===null||t===undefined||t===""?(fallback||"—"):safe(t)}
function formatMoney(value){var n=Number(value);return Number.isFinite(n)?new Intl.NumberFormat("ru-RU",{maximumFractionDigits:2}).format(n)+" сом":"—"}
function formatDate(v){if(!v)return "—";var d=new Date(v+"T00:00:00");return isNaN(d.getTime())?safe(v):new Intl.DateTimeFormat("ru-RU",{day:"2-digit",month:"short",year:"numeric"}).format(d)}
function formatDateTime(value){if(!value)return "—";var raw=String(value);if(!(/[zZ]$|[+-]\d\d:\d\d$/.test(raw)))raw+="Z";var d=new Date(raw);return isNaN(d.getTime())?"—":new Intl.DateTimeFormat("ru-RU",{timeZone:"Asia/Bishkek",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(d)}
function statusTag(value){var v=String(value||"").toLowerCase(),ok=["active","confirmed","completed","approved"].includes(v),pending=["pending"].includes(v);var labels={active:"Активный",confirmed:"Подтверждён",completed:"Завершён",approved:"Одобрено",pending:"В ожидании",rejected:"Отклонён",cancelled:"Отменён"};return '<span class="pill '+(ok?"active":pending?"pending":"")+'">'+safe(labels[v]||v||"—")+"</span>"}
// Временный знак именно EduFlow, а не выдуманный «официальный» логотип Motion Web.
function logo(){return '<span class="brand-mark eduflow-brand-mark" aria-hidden="true">E<span class="brand-dot"></span></span>'}
function brand(){return '<div class="brand">'+logo()+'<span class="brand-wordmark">EduFlow<small>Motion Web Academy</small></span></div>'}
function prefsKey(key){return "eduflow."+key+(state.user?"."+state.user.username:"")}
function loadUserPrefs(){if(!state.user)return;var theme=localStorage.getItem(prefsKey("theme")),accent=localStorage.getItem(prefsKey("accent"));if(theme==="light"||theme==="dark")pref.theme=theme;if(COLORS.includes(accent))pref.accent=accent}
function applyTheme(){document.body.dataset.theme=pref.theme;document.body.dataset.accent=pref.accent;localStorage.setItem(prefsKey("theme"),pref.theme);localStorage.setItem(prefsKey("accent"),pref.accent)}
function setTheme(t){pref.theme=t;applyTheme();render()}
function setAccent(c){if(!COLORS.includes(c))return;pref.accent=c;applyTheme();render()}
function palette(){return '<div class="theme-swatches">'+COLORS.map(function(c){return '<button class="swatch '+(pref.accent===c?"selected":"")+'" data-action="accent" data-color="'+c+'" aria-label="Акцент '+c+'" title="'+c+'"></button>'}).join("")+'</div>'}
function themeBtns(){return '<div class="theme-mode"><button class="'+(pref.theme==="light"?"selected":"")+'" data-action="theme" data-value="light">'+ico("sun")+' День</button><button class="'+(pref.theme==="dark"?"selected":"")+'" data-action="theme" data-value="dark">'+ico("moon")+' Ночь</button></div>'}
function authHeaders(){return {"Authorization":"Bearer "+state.token}}
async function request(path,opts){opts=opts||{};var headers=Object.assign({},authHeaders(),opts.headers||{});var response=await fetch(path,Object.assign({},opts,{headers:headers,cache:"no-store"}));if(response.status===401){signOut(false);throw Error("Сессия истекла. Войдите ещё раз.")}if(!response.ok){var reason="Ошибка сервера: "+response.status;try{var obj=await response.json();if(typeof obj.detail==="string")reason=obj.detail}catch(e){}throw Error(reason)}if(response.status===204)return null;return response.json()}
async function optionalRequest(path,fallback){try{return await request(path)}catch(e){if(e.message.indexOf("Сессия истекла")>=0)throw e;return fallback}}
function toast(message){var n=el("toast");if(n)n.remove();n=document.createElement("div");n.id="toast";n.className="toast";n.textContent=message;document.body.appendChild(n);setTimeout(function(){n.remove()},4200)}
function isAdmin(){return !!(state.user&&state.user.role==="admin")}
function myStudent(){return !isAdmin()&&state.profile?state.profile:null}
function findGroup(id){return state.groups.find(function(g){return Number(g.id)===Number(id)})}
function findStudent(id){return state.students.find(function(s){return Number(s.id)===Number(id)})}
function studentName(s){if(!s)return "Студент";var p=s.personal_info||{};return [p.last_name,p.first_name,p.middle_name].filter(Boolean).join(" ")||"Студент №"+s.student_number}
function countInGroup(id){return state.students.filter(function(s){return Number(s.group_id)===Number(id)}).length}
function paymentPaid(contract){return state.payments.filter(function(p){return p.contract_id===contract.id&&p.status==="confirmed"}).reduce(function(a,p){return a+Number(p.amount)},0)}
function contractBalance(c){var b=state.balances.find(function(b){return b.contract_id===c.id});if(b)return b;var paid=paymentPaid(c);return {paid_amount:paid,remaining_amount:Number(c.total_amount)-paid,total_amount:c.total_amount}}
function groupOfStudent(s){return findGroup(s&&s.group_id)}
function navBtn(name,label,icon){return '<button class="nav-link '+(state.view===name?"active":"")+'" data-go="'+name+'">'+ico(icon)+'<span>'+label+'</span></button>'}
function sidebar(){return '<aside class="sidebar"><div class="brand-header">'+brand()+'<div class="brand-caption">EduFlow learning platform</div></div><nav class="nav" aria-label="Навигация">'+navBtn("dashboard","Главная","home")+(isAdmin()?navBtn("students","Студенты","users")+navBtn("groups","Группы","grid"):"")+navBtn("contracts","Контракты","doc")+navBtn("payments","Платежи","wallet")+navBtn("schedule","Расписание","calendar")+(!isAdmin()?navBtn("grades","Оценки / Табель","graduation")+navBtn("profile","Мой профиль","user"):"")+navBtn("settings","Настройки","settings")+'</nav><div class="sidebar-bottom"><a class="nav-link" href="https://portalmotionweb.com/#/my-grades" target="_blank" rel="noopener noreferrer">'+ico("link")+'Открыть Tabel</a><button class="nav-link" data-action="logout">'+ico("logout")+'Выйти</button></div></aside>'}
function topbar(){return '<header class="topbar"><button class="icon-btn mobile-open" data-action="menu" aria-label="Открыть меню">'+ico("menu")+'</button><div class="top-name"><strong>'+(isAdmin()?"Главная":"Личный кабинет")+'</strong><span class="muted small">'+(isAdmin()?"Администрирование":"Моё обучение")+'</span></div><div class="top-tools">'+(isAdmin()?'<label class="searchbox">'+ico("search")+'<input id="top-search" type="search" placeholder="Поиск студентов..." aria-label="Поиск студентов"></label>':"")+'<button class="icon-btn" data-go="settings" title="Оформление">'+ico(pref.theme==="dark"?"moon":"sun")+'</button><div class="identity"><span class="avatar">'+safe((state.user.username||"U").slice(0,2).toUpperCase())+'</span><span>'+safe(state.user.username)+'</span></div></div></header>'}
function heading(title,description,action){return '<div class="headline"><div><h1>'+safe(title)+'</h1><p>'+safe(description||"")+'</p></div>'+(action||"")+'</div>'}
function empty(title,description){return '<div class="empty">'+ico("info")+'<strong>'+safe(title)+'</strong><div>'+safe(description||"")+'</div></div>'}
function action(text,go,secondary){return '<button class="btn '+(secondary?"secondary":"")+'" data-go="'+go+'">'+safe(text)+ico("arrow")+'</button>'}
function row(title,subtitle,end){return '<div class="tile"><div><strong>'+safe(title)+'</strong><span class="muted">'+safe(subtitle||"")+'</span></div>'+(end||"")+'</div>'}
function card(title,inner,extra){return '<section class="card"><div class="card-head"><h2>'+safe(title)+'</h2>'+(extra||"")+'</div>'+inner+'</section>'}
function dashboardIntro(title,description){
  var now=new Intl.DateTimeFormat("ru-RU",{timeZone:"Asia/Bishkek",weekday:"long",day:"numeric",month:"long"}).format(new Date());
  return '<header class="dashboard-intro"><div><span class="dashboard-date">'+safe(now)+'</span><h1>'+safe(title)+'</h1><p>'+safe(description||"")+'</p></div></header>';
}
function dashboardMetric(label,value,detail,icon,go){
  return '<button type="button" class="dashboard-metric" data-go="'+go+'"><span class="metric-icon">'+ico(icon)+'</span><span class="metric-copy"><strong>'+safe(label)+'</strong><span>'+safe(detail)+'</span></span><span class="metric-value">'+safe(value)+'</span>'+ico("arrow")+'</button>';
}
function adminDashboard(){
  var pending=state.payments.filter(function(p){return p.status==="pending"});
  var confirmed=state.payments.filter(function(p){return p.status==="confirmed"});
  var rejected=state.payments.filter(function(p){return p.status==="rejected"});
  var paid=confirmed.reduce(function(a,p){return a+Number(p.amount)},0);
  var pendingSum=pending.reduce(function(a,p){return a+Number(p.amount)},0);
  var activeContracts=state.contracts.filter(function(c){return c.status==="active"}).length;
  var recent=pending.slice().reverse().slice(0,5);
  var rows=recent.length?'<div class="table-wrap"><table class="table"><thead><tr><th>Студент</th><th>Месяц</th><th>Сумма</th><th>Дата</th><th>Статус</th></tr></thead><tbody>'+recent.map(function(p){
    var c=state.contracts.find(function(c){return c.id===p.contract_id});
    var student=c?findStudent(c.student_id):null;
    return '<tr><td>'+safe(student?studentName(student):"Контракт #"+p.contract_id)+'</td><td>'+safe(p.payment_month||"—")+'</td><td>'+formatMoney(p.amount)+'</td><td>'+formatDateTime(p.created_at)+'</td><td>'+statusTag(p.status)+'</td></tr>';
  }).join("")+'</tbody></table></div>':empty("Нет платежей на проверке","Новые платежи появятся здесь автоматически.");
  return dashboardIntro("Добрый день, "+state.user.username,"Панель управления академией")
  +'<div class="dashboard-finance">'
  +'<section class="card dashboard-feature"><div class="feature-heading"><span>ТРЕБУЮТ ПРОВЕРКИ</span>'+ico("wallet")+'</div><div class="feature-number">'+pending.length+'<small> платежей</small></div><div class="feature-foot">На сумму '+formatMoney(pendingSum)+'</div><button class="btn feature-action" data-go="payments">Перейти к платежам '+ico("arrow")+'</button></section>'
  +'<section class="card dashboard-stat"><div class="stat-label">Подтверждено оплат</div><div class="stat-number">'+formatMoney(paid)+'</div><p>'+activeContracts+' активных контрактов</p><span class="stat-bottom">'+ico("check")+' Подтверждённые операции</span></section>'
  +'<section class="card dashboard-stat"><div class="stat-label">Все платежи</div><div class="stat-number">'+state.payments.length+'</div><p>'+confirmed.length+' подтверждено · '+pending.length+' на проверке</p><div class="status-bars"><i style="width:'+(state.payments.length?100*confirmed.length/state.payments.length:0)+'%"></i><i style="width:'+(state.payments.length?100*pending.length/state.payments.length:0)+'%"></i><i style="width:'+(state.payments.length?100*rejected.length/state.payments.length:0)+'%"></i></div></section>'
  +'</div>'
  +'<div class="dashboard-metrics">'
  +dashboardMetric("Студенты",state.students.length,"В системе","users","students")
  +dashboardMetric("Группы",state.groups.length,"Учебные группы","grid","groups")
  +dashboardMetric("Контракты",activeContracts,"Активные","doc","contracts")
  +dashboardMetric("Платежи",state.payments.length,"Всего операций","wallet","payments")
  +'</div>'
  +'<section class="card dashboard-table"><div class="card-head"><h2>Новые платежи на проверке</h2><button class="link" data-go="payments">Все платежи '+ico("arrow")+'</button></div>'+rows+'</section>';
}
function studentDashboard(){
  var s=myStudent(),g=groupOfStudent(s);
  var balance=state.balances.reduce(function(a,b){return a+Number(b.remaining_amount)},0);
  var confirmed=state.payments.filter(function(p){return p.status==="confirmed"});
  var avg=state.study&&state.study.average_grade!=null?state.study.average_grade:"—";
  var lessons=g&&g.schedules?g.schedules:[];
  var schedule=lessons.length?lessons.slice(0,5).map(function(sc){
    return row(sc.title,weekday(sc.weekday),'<span class="pill">'+safe(sc.start_time.slice(0,5))+'–'+safe(sc.end_time.slice(0,5))+'</span>');
  }).join(""):empty("Расписания пока нет","Занятия появятся после назначения группы.");
  return dashboardIntro("Здравствуйте, "+studentName(s),"Ваши занятия, контракты и платежи")
    +'<div class="dashboard-metrics student-metrics">'
    +dashboardMetric("Моя группа",g?g.name:"—",g?g.course_name:"Группа не назначена","grid","schedule")
    +dashboardMetric("Контракты",state.contracts.length,"Мои договоры","doc","contracts")
    +dashboardMetric("Оплачено",confirmed.length,"Подтверждённых платежей","wallet","payments")
    +dashboardMetric("Средняя оценка",avg,"Успеваемость","graduation","grades")
    +'</div>'
    +'<div class="student-overview"><section class="card balance-panel"><span class="stat-label">Остаток по контрактам</span><div class="stat-number">'+formatMoney(balance)+'</div><p>По данным подтверждённых платежей</p><button class="btn secondary" data-go="contracts">Мои контракты '+ico("arrow")+'</button></section>'
    +card("Расписание",schedule,'<button class="link" data-go="schedule">Открыть '+ico("arrow")+'</button>')
    +'</div>';
}
function kpi(label,value,icon,note){return '<div class="card kpi accent-card"><div class="kpi-label">'+ico(icon)+safe(label)+'</div><div class="kpi-value">'+safe(value)+'</div><small>'+safe(note||"")+'</small></div>'}
function studentDashboard(){var s=myStudent(),g=groupOfStudent(s),bal=state.balances.reduce(function(a,b){return a+Number(b.remaining_amount)},0);var avg=state.study&&state.study.average_grade?state.study.average_grade:"—";var percentage=state.study&&state.study.progress_percent!=null?Number(state.study.progress_percent):null;return '<section class="card hero"><div class="hero-content"><div class="hero-kicker">Добро пожаловать</div><h1>'+safe(studentName(s))+' 👋</h1><p>Ваше обучение, успеваемость и финансовая информация в одном кабинете.</p></div></section><div class="kpis">'+kpi("Моя группа",g?g.name:"—","grid","Текущая учебная группа")+kpi("Средняя оценка",avg,"graduation","Из системы Tabel, если подключена")+kpi("Прогресс",percentage===null?"—":percentage+"%","chart","По учебному порталу")+kpi("Остаток по контрактам",formatMoney(bal),"wallet","По данным подтверждённых платежей")+'</div><div class="cols-2">'+card("Расписание группы",g&&g.schedules&&g.schedules.length?g.schedules.slice(0,5).map(function(sc){return row(sc.title,weekday(sc.weekday),'<span class="pill">'+safe(sc.start_time.slice(0,5))+' — '+safe(sc.end_time.slice(0,5))+'</span>')}).join(""):empty("Расписание отсутствует","Занятия появятся после настройки расписания."),action("Расписание","schedule",true))+card("Мои контракты",state.contracts.length?state.contracts.map(function(c){return row("Контракт #"+c.id,formatMoney(c.total_amount)+' · '+statusText(c.status),'<button class="link" data-contract="'+c.id+'">Подробнее '+ico("arrow")+'</button>')}).join(""):empty("Контрактов пока нет","Информация появится после оформления контракта."),action("Все контракты","contracts",true))+'</div><div style="margin-top:18px" class="cols-2">'+card("Табель и успеваемость",state.study?'<div class="info-grid">'+infoItem("Посещено занятий",state.study.attended_lessons+" / "+state.study.held_lessons)+infoItem("Посещаемость",state.study.attendance_percent==null?"—":state.study.attendance_percent+"%")+infoItem("Оценки",(state.study.grades||[]).join(", ")||"—")+infoItem("Средняя оценка",avg)+'</div>':empty("Интеграция с Tabel не настроена","Посмотрите оценки в действующем портале Motion Web."),'<a href="https://portalmotionweb.com/#/my-grades" rel="noopener noreferrer" target="_blank" class="link">Tabel '+ico("link")+'</a>')+card("Фотография профиля",photoWidget(s))+'</div>'}
function statusText(v){return {active:"Активный",completed:"Завершён",cancelled:"Отменён"}[v]||v||"—"}
function weekday(v){return {Monday:"Понедельник",Tuesday:"Вторник",Wednesday:"Среда",Thursday:"Четверг",Friday:"Пятница",Saturday:"Суббота",Sunday:"Воскресенье"}[v]||v}
function listStudents(rows){if(!rows.length)return empty("Студентов не найдено","Попробуйте другой запрос или проверьте выбранную группу.");return '<div class="table-wrap"><table class="table"><thead><tr><th>Студент</th><th>Номер</th><th>Группа</th><th>Контракты</th><th></th></tr></thead><tbody>'+rows.map(function(s){var g=groupOfStudent(s);return '<tr><td><button data-student="'+s.id+'">'+safe(studentName(s))+'</button></td><td>'+safe(s.student_number)+'</td><td>'+(g?'<button data-group="'+g.id+'">'+safe(g.name)+'</button>':"—")+'</td><td>'+state.contracts.filter(function(c){return c.student_id===s.id}).length+'</td><td><button class="link" data-student="'+s.id+'">Открыть '+ico("arrow")+'</button></td></tr>'}).join("")+'</tbody></table></div>'}
function studentsView(){return heading("Студенты","Выберите студента, чтобы посмотреть профиль, группу и контракты.")+'<section class="card"><div class="filters"><input class="field" id="students-filter" placeholder="Поиск по имени или номеру..." aria-label="Поиск студентов"><select class="select" id="group-filter" aria-label="Фильтр по группе"><option value="">Все группы</option>'+state.groups.map(function(g){return '<option value="'+g.id+'">'+safe(g.name)+'</option>'}).join("")+'</select></div><div id="students-results">'+listStudents(state.students)+'</div></section>'}
function groupsView(){return heading("Группы","Нажмите на группу, чтобы увидеть всех её студентов.")+(state.groups.length?'<div class="group-cards">'+state.groups.map(function(g){return '<button class="card group-card" data-group="'+g.id+'"><span class="icon-surface">'+ico("grid")+'</span><h2>'+safe(g.name)+'</h2><span class="muted">'+safe(g.course_name)+' · Ментор: '+text(g.mentor_name)+'</span><div class="bottom"><span>'+countInGroup(g.id)+' студентов</span><span class="accent-text">'+ico("arrow")+'</span></div></button>'}).join("")+'</div>':card("Группы",empty("Групп пока нет","Они отобразятся здесь автоматически после добавления.")))}
function groupView(){var g=findGroup(state.selected);if(!g)return notFound("Группа");var students=state.students.filter(function(s){return s.group_id===g.id});return '<button class="back" data-go="groups">'+ico("back")+' Назад к группам</button>'+heading(g.name,g.course_name+' · '+students.length+' студентов')+'<div class="cols-2">'+card("Информация о группе",'<div class="info-grid">'+infoItem("Название",g.name)+infoItem("Курс",g.course_name)+infoItem("Ментор",g.mentor_name)+infoItem("Начало обучения",formatDate(g.start_date))+infoItem("Окончание",formatDate(g.end_date))+'</div>')+card("Расписание",g.schedules&&g.schedules.length?g.schedules.map(function(sc){return row(sc.title,weekday(sc.weekday),'<span class="pill">'+safe(sc.start_time.slice(0,5))+'</span>')}).join(""):empty("Нет расписания","Занятия пока не добавлены."))+'</div><div style="margin-top:18px">'+card("Студенты группы",listStudents(students))+'</div>'}
function notFound(type){return '<button class="back" data-go="dashboard">'+ico("back")+' На главную</button>'+empty(type+" не найдена","Проверьте выбранную запись.")}
function infoItem(label,value){return '<div class="info-item"><span>'+safe(label)+'</span><strong>'+safe(value)+'</strong></div>'}
function detailStudentView(){var s=findStudent(state.selected);if(!s)return notFound("Студент");var g=groupOfStudent(s),p=s.personal_info||{},contracts=state.contracts.filter(function(c){return c.student_id===s.id});var history=s.group_history||[];return '<button class="back" data-go="students">'+ico("back")+' Назад к студентам</button><div class="breadcrumb">Студенты / <span>'+safe(studentName(s))+'</span></div><div class="card detail-header" style="margin-bottom:18px"><span class="avatar big-avatar">'+safe((p.first_name||"S").slice(0,1))+'</span><div><h1>'+safe(studentName(s))+'</h1><p>Студент № '+safe(s.student_number)+' · '+safe(g?g.name:"Без группы")+'</p></div></div><div class="cols-2">'+card("Личные данные",'<div class="info-grid">'+infoItem("Фамилия",p.last_name)+infoItem("Имя",p.first_name)+infoItem("Отчество",p.middle_name)+infoItem("Телефон",p.phone)+infoItem("Дата рождения",formatDate(p.birth_date))+infoItem("Место рождения",p.birth_place)+infoItem("Адрес",p.address)+infoItem("Адрес регистрации",p.registration_address)+'</div>')+card("Обучение",'<div class="info-grid">'+infoItem("Номер студента",s.student_number)+infoItem("Группа",g?g.name:"Не назначена")+infoItem("Курс",g?g.course_name:"—")+infoItem("Ментор группы",s.mentor_name||(g&&g.mentor_name))+infoItem("Начало обучения",g?formatDate(g.start_date):"—")+'</div>'+(g?'<div class="separator"></div><button class="btn secondary" data-group="'+g.id+'">Перейти к группе '+ico("arrow")+'</button>':""))+'</div><div style="margin-top:18px" class="cols-2">'+card("Контракты",contracts.length?contracts.map(function(c){var b=contractBalance(c);return row("Контракт #"+c.id+" · "+statusText(c.status),"Сумма: "+formatMoney(c.total_amount)+" · Остаток: "+formatMoney(b.remaining_amount),'<button class="link" data-contract="'+c.id+'">Открыть '+ico("arrow")+'</button>')}).join(""):empty("Контрактов пока нет","Когда контракт будет добавлен, он появится здесь."))+card("История групп",history.length?history.map(function(h){var hg=findGroup(h.group_id);return row(hg?hg.name:"Группа #"+h.group_id,formatDate(h.from_date)+" — "+(h.to_date?formatDate(h.to_date):"по настоящее время"),h.to_date?"":'<span class="pill active">Текущая</span>')}).join(""):empty("История отсутствует","Данные о переводах пока не сохранены."))+'</div>'}
function contractsView(){return heading("Контракты","Информация о стоимости обучения, статусах и остатках.")+card("Список контрактов",state.contracts.length?'<div class="table-wrap"><table class="table"><thead><tr><th>Контракт</th>'+(isAdmin()?"<th>Студент</th>":"")+'<th>Стоимость</th><th>Оплачено</th><th>Остаток</th><th>Статус</th><th></th></tr></thead><tbody>'+state.contracts.map(function(c){var b=contractBalance(c),s=findStudent(c.student_id);return '<tr><td>#'+c.id+'</td>'+(isAdmin()?'<td>'+(s?safe(studentName(s)):"—")+'</td>':"")+'<td>'+formatMoney(c.total_amount)+'</td><td>'+formatMoney(b.paid_amount)+'</td><td>'+formatMoney(b.remaining_amount)+'</td><td>'+statusTag(c.status)+'</td><td><button class="link" data-contract="'+c.id+'">Подробнее '+ico("arrow")+'</button></td></tr>'}).join("")+'</tbody></table></div>':empty("Контрактов пока нет","Оформленные контракты будут доступны здесь."))}
function contractView(){var c=state.contracts.find(function(x){return x.id===Number(state.selected)});if(!c)return notFound("Контракт");var s=findStudent(c.student_id),b=contractBalance(c),p=state.payments.filter(function(p){return p.contract_id===c.id});var percent=Number(c.total_amount)>0?Math.max(0,Math.min(100,100*Number(b.paid_amount)/Number(c.total_amount))):0;return '<button class="back" data-go="contracts">'+ico("back")+' Назад к контрактам</button>'+heading("Контракт #"+c.id,"Детали и финансовые операции.")+'<div class="kpis">'+kpi("Полная сумма",formatMoney(c.total_amount),"doc","")+kpi("Оплачено",formatMoney(b.paid_amount),"wallet","")+kpi("Остаток",formatMoney(b.remaining_amount),"chart","")+kpi("Ежемесячный платёж",formatMoney(c.monthly_payment),"calendar","")+'</div><div class="cols-2">'+card("Информация о контракте",'<div class="info-grid">'+infoItem("Студент",s?studentName(s):"ID "+c.student_id)+infoItem("Тип",c.type==="college"?"Колледж":"Академия")+infoItem("Статус",statusText(c.status))+infoItem("Дата начала",formatDate(c.start_date))+infoItem("Срок",c.duration_months+" мес.")+infoItem("График оплаты",c.type==="college"?((c.installment_count||2)+" взноса"):"Ежемесячно")+infoItem("День оплаты",c.payment_day||"—")+'</div><div class="separator"></div><div class="row space"><strong>Оплачено</strong><span>'+percent.toFixed(0)+'%</span></div><div class="progress"><i style="width:'+percent+'%"></i></div>'+(isAdmin()&&s?'<button class="link" data-student="'+s.id+'">Профиль студента '+ico("arrow")+'</button>':""))+card("История платежей",p.length?p.map(function(x){return row(formatMoney(x.amount),((x.allocations||[]).map(function(a){return a.payment_month||("Взнос "+(a.period_index+1))}).join(", ")||x.payment_month)+" · "+(x.payment_method||"—"),statusTag(x.status))}).join(""):empty("Платежей пока нет","Операции появятся после оплаты."))+'</div>'}
function paymentsView(){return heading("Платежи","Отображаются реальные операции, полученные через API.")+card("История платежей",state.payments.length?'<div class="table-wrap"><table class="table"><thead><tr><th>Номер</th><th>Контракт</th><th>Сумма</th><th>Месяц</th><th>Метод</th><th>Дата / время (Бишкек)</th><th>Статус</th></tr></thead><tbody>'+state.payments.slice().reverse().map(function(p){return '<tr><td>#'+p.id+'</td><td><button data-contract="'+p.contract_id+'">#'+p.contract_id+'</button></td><td>'+formatMoney(p.amount)+'</td><td>'+safe(p.payment_month)+'</td><td>'+safe(p.payment_method||"—")+'</td><td>'+formatDateTime(p.paid_at||p.created_at)+'</td><td>'+statusTag(p.status)+'</td></tr>'}).join("")+'</tbody></table></div>':empty("История пуста","Подтверждённые и ожидающие платежи появятся здесь."))}
function scheduleView(){var groups=isAdmin()?state.groups:state.groups.slice(0,1),all=groups.flatMap(function(g){return (g.schedules||[]).map(function(sc){return {group:g,entry:sc}})});var days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];all.sort(function(a,b){return days.indexOf(a.entry.weekday)-days.indexOf(b.entry.weekday)||a.entry.start_time.localeCompare(b.entry.start_time)});return heading("Расписание","Занятия по группам и дням недели.")+card("Занятия",all.length?'<div class="table-wrap"><table class="table"><thead><tr><th>День</th><th>Занятие</th><th>Группа</th><th>Время</th></tr></thead><tbody>'+all.map(function(x){return '<tr><td>'+safe(weekday(x.entry.weekday))+'</td><td>'+safe(x.entry.title)+'</td><td>'+(isAdmin()?'<button data-group="'+x.group.id+'">'+safe(x.group.name)+'</button>':safe(x.group.name))+'</td><td>'+safe(x.entry.start_time.slice(0,5))+' – '+safe(x.entry.end_time.slice(0,5))+'</td></tr>'}).join("")+'</tbody></table></div>':empty("Расписание пока не добавлено","Уточните расписание у администрации."))}
function gradesView(){return heading("Оценки и Tabel","Просмотр оценок из действующего портала Motion Web.")+'<div class="cols-2">'+card("Успеваемость",state.study?'<div class="info-grid">'+infoItem("Средняя оценка",state.study.average_grade)+infoItem("Посещаемость",state.study.attendance_percent==null?"—":state.study.attendance_percent+"%")+infoItem("Оценки",(state.study.grades||[]).join(", ")||"—")+infoItem("Прогресс",state.study.progress_percent==null?"—":state.study.progress_percent+"%")+'</div>':empty("Связь с Tabel ещё не настроена","Данные не подменяются демонстрационными."))+card("Motion Web Tabel",'<p class="muted">Для полного доступа к табелю откройте действующий портал. Единая авторизация пока не внедрена.</p><a class="btn" href="https://portalmotionweb.com/#/my-grades" target="_blank" rel="noopener noreferrer">Открыть Tabel '+ico("link")+'</a>')+'</div>'}
function photoWidget(s){return '<p class="muted small" style="margin:0 0 12px">Загрузите JPG или PNG (до 2 МБ). Изображение сохраняется в EduFlow.</p><label class="photo-drop" for="profile-upload">'+(state.photoUrl?'<img class="preview-photo" src="'+state.photoUrl+'" alt="Фото профиля">':ico("upload"))+'<strong>'+(state.photoUrl?"Изменить фото":"Добавить фотографию")+'</strong><span>Нажмите для выбора файла</span></label><input type="file" accept="image/png,image/jpeg" id="profile-upload" class="file-upload">'}
function profileView(){var s=myStudent(),p=s&&s.personal_info||{},g=groupOfStudent(s);return heading("Мой профиль","Личные данные и фотография.")+'<div class="cols-2">'+card("Личные данные",'<div class="info-grid">'+infoItem("Имя",p.first_name)+infoItem("Фамилия",p.last_name)+infoItem("Отчество",p.middle_name)+infoItem("Телефон",p.phone)+infoItem("Дата рождения",formatDate(p.birth_date))+infoItem("Номер студента",s.student_number)+infoItem("Группа",g?g.name:"—")+infoItem("Ментор",s.mentor_name||(g&&g.mentor_name))+infoItem("Адрес",p.address)+'</div>')+card("Фотография",photoWidget(s))+'</div>'}
function settingsView(){return heading("Настройки оформления","Выберите удобный режим и цвет подсветки. Настройки сохраняются только в этом браузере.")+'<div class="cols-2">'+card("Режим экрана",'<p class="muted">Дневной режим с белыми карточками или ночной режим с неоновой подсветкой.</p>'+themeBtns())+card("Цвет акцента",'<p class="muted">Выберите любимый цвет. Он применяется к кнопкам, активному меню и свечению карточек.</p>'+palette())+'</div><div style="margin-top:18px">'+card("Motion Web",'<div class="row">'+logo()+'<div><strong>EduFlow / Motion Web Academy</strong><p class="muted small">Оформление не меняет данные и права доступа.</p></div></div>')+'</div>'}
function viewMarkup(){switch(state.view){case "dashboard":return isAdmin()?adminDashboard():studentDashboard();case "students":return isAdmin()?studentsView():notFound("Раздел");case "groups":return isAdmin()?groupsView():notFound("Раздел");case "group":return isAdmin()?groupView():notFound("Группа");case "student":return isAdmin()?detailStudentView():notFound("Студент");case "contracts":return contractsView();case "contract":return contractView();case "payments":return paymentsView();case "schedule":return scheduleView();case "grades":return !isAdmin()?gradesView():notFound("Раздел");case "profile":return !isAdmin()?profileView():notFound("Раздел");case "settings":return settingsView();default:return adminDashboard()}}
function layout(){return '<div class="layout" id="layout">'+sidebar()+'<main class="main">'+topbar()+'<div class="content">'+(state.loadError?'<div class="notice error-notice" style="margin-bottom:18px">'+safe(state.loadError)+' <button class="link" data-action="reload">Повторить</button></div>':"")+viewMarkup()+'</div></main></div>'}
function loginView(){
  return '<div class="login login-minimal">'
    +'<div class="login-theme">'+themeBtns()+'</div>'
    +'<div class="login-center">'
    +'<div class="login-brand">'+brand()+'</div>'
    +'<section class="login-form-wrap login-card">'
      +'<div class="login-form-top"><h1 class="login-title">Вход в EduFlow</h1><p>Введите логин и пароль вашего аккаунта.</p></div>'
      +'<form id="login-form">'
        +'<div class="form-row"><label for="login-username" class="form-label">Логин</label><div class="login-field-wrap">'+ico("user")+'<input id="login-username" class="field" name="username" autocomplete="username" required maxlength="50" placeholder="Ваш логин"></div></div>'
        +'<div class="form-row"><label for="login-password" class="form-label">Пароль</label><div class="login-field-wrap">'+ico("lock")+'<input id="login-password" class="field" name="password" autocomplete="current-password" type="password" required maxlength="128" placeholder="Ваш пароль"><button type="button" class="password-toggle" data-action="toggle-password" aria-label="Показать пароль" aria-pressed="false">'+ico("eye")+'</button></div></div>'
        +'<div class="form-error" id="login-error" role="alert" aria-live="polite"></div>'
        +'<button class="btn wide login-submit-btn" id="login-submit" type="submit">Войти '+ico("arrow")+'</button>'
      +'</form>'
      +'<a class="demo-preview-link" href="/app/preview.html">Посмотреть интерфейс <span>Демо, без реальных данных</span></a>'
    +'</section>'
    +'<footer class="login-copyright">EduFlow · Motion Web Academy</footer>'
    +'</div></div>';
}
function render(){applyTheme();app.innerHTML=state.user?layout():loginView();if(state.user&&state.view==="students")applyStudentsFilter()}
function navigate(view,id){state.view=view;state.selected=id||null;window.location.hash="#/"+view+(id?"/"+id:"");render();window.scrollTo(0,0)}
function syncHash(){if(!state.user)return;var m=location.hash.match(/^#\/(dashboard|students|groups|group|student|contracts|contract|payments|schedule|grades|profile|settings)(?:\/(\d+))?$/);if(m){if(!isAdmin()&&["students","groups","group","student"].includes(m[1])){navigate("dashboard");return}state.view=m[1];state.selected=m[2]?Number(m[2]):null}render()}
async function loadData(){state.loadError=null;state.loading=true;try{if(isAdmin()){var r=await Promise.all([request("/students/"),request("/groups/"),request("/contracts/"),request("/payments/")]);state.students=r[0];state.groups=r[1];state.contracts=r[2];state.payments=r[3];state.balances=[]}else{var s=await request("/students/me");state.profile=s;state.students=[s];var r=await Promise.all([optionalRequest("/groups/my",null),request("/contracts/my"),request("/payments/my"),request("/payments/my/balance"),optionalRequest("/study/me",null)]);state.groups=r[0]?[r[0]]:[];state.contracts=r[1];state.payments=r[2];state.balances=r[3];state.study=r[4];loadMyPhoto(s.id)}state.ready=true}catch(e){state.loadError=e.message;state.ready=false}finally{state.loading=false;render()}}
async function loadMyPhoto(id){if(!state.token)return;try{var r=await fetch("/students/"+id+"/photo",{headers:authHeaders(),cache:"no-store"});if(!r.ok)return;var b=await r.blob();if(state.photoUrl)URL.revokeObjectURL(state.photoUrl);state.photoUrl=URL.createObjectURL(b);if(state.view==="profile"||state.view==="dashboard")render()}catch(e){}}
async function doLogin(form){
  var submit=el("login-submit"), msg=el("login-error");
  if(!submit||!msg)return;
  submit.disabled=true;
  msg.textContent="";
  try{
    var username=form.elements.namedItem("username").value.trim();
    var password=form.elements.namedItem("password").value;
    var response=await fetch("/auth/login",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({username:username,password:password}),
      cache:"no-store"
    });
    var data=null;
    try{data=await response.json()}catch(e){}
    if(!response.ok){
      if(response.status===401)throw Error("Неверный логин или пароль. Возможно, сервер подключён к другой базе данных.");
      if(response.status===403)throw Error("Аккаунт отключён. Обратитесь к администратору.");
      if(response.status>=500)throw Error("Сервер временно недоступен. Проверьте подключение к PostgreSQL.");
      throw Error(data&&typeof data.detail==="string"?data.detail:"Ошибка входа: "+response.status);
    }
    if(!data||!data.access_token)throw Error("Сервер вернул некорректный ответ.");
    state.token=data.access_token;
    state.refresh=data.refresh_token;
    state.user=await request("/auth/me");
    loadUserPrefs();
    state.view="dashboard";
    state.selected=null;
    location.hash="#/dashboard";
    render();
    await loadData();
  }catch(e){
    state.token=null;state.refresh=null;state.user=null;
    render();
    var error=el("login-error");
    if(error)error.textContent=e instanceof TypeError?"Нет связи с сервером. Проверьте, что FastAPI запущен.":(e.message||"Ошибка входа");
  }finally{
    var b=el("login-submit");
    if(b)b.disabled=false;
  }
}
async function signOut(revoke){var refresh=state.refresh,access=state.token;if(revoke&&refresh&&access){try{await fetch("/auth/logout",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+access},body:JSON.stringify({refresh_token:refresh}),cache:"no-store"})}catch(e){}}state.token=null;state.refresh=null;state.user=null;state.students=[];state.groups=[];state.contracts=[];state.payments=[];state.profile=null;state.study=null;state.balances=[];state.loadError=null;state.view="dashboard";if(state.photoUrl)URL.revokeObjectURL(state.photoUrl);state.photoUrl=null;location.hash="";render()}
function applyStudentsFilter(){var inp=el("students-filter"),sel=el("group-filter"),target=el("students-results");if(!inp||!sel||!target)return;var q=inp.value.trim().toLocaleLowerCase(),group=sel.value;var found=state.students.filter(function(s){return (!group||String(s.group_id)===group)&&(!q||studentName(s).toLocaleLowerCase().includes(q)||String(s.student_number).toLocaleLowerCase().includes(q))});target.innerHTML=listStudents(found)}
async function uploadPhoto(file){if(!file||!state.profile)return;if(!["image/jpeg","image/png"].includes(file.type)){toast("Разрешены JPG и PNG");return}if(file.size>2*1024*1024){toast("Файл должен быть не больше 2 МБ");return}var form=new FormData();form.append("file",file);try{await request("/students/me/photo",{method:"PUT",body:form});toast("Фотография обновлена");await loadMyPhoto(state.profile.id)}catch(e){toast(e.message)}}
document.addEventListener("submit",function(e){if(e.target.id==="login-form"){e.preventDefault();doLogin(e.target)}});
document.addEventListener("click",function(e){var a=e.target.closest("[data-action],[data-go],[data-group],[data-student],[data-contract]");if(!a)return;if(a.dataset.action==="toggle-password"){var pass=el("login-password");if(pass){var showing=pass.type==="password";pass.type=showing?"text":"password";a.setAttribute("aria-label",showing?"Скрыть пароль":"Показать пароль");a.setAttribute("aria-pressed",String(showing));a.innerHTML=ico(showing?"eye-off":"eye");pass.focus()}return}if(a.dataset.action==="theme"){setTheme(a.dataset.value);return}if(a.dataset.action==="accent"){setAccent(a.dataset.color);return}if(a.dataset.action==="logout"){signOut(true);return}if(a.dataset.action==="reload"){loadData();return}if(a.dataset.action==="menu"){el("layout").classList.toggle("menu-open");return}if(a.dataset.group){navigate("group",Number(a.dataset.group));return}if(a.dataset.student){navigate("student",Number(a.dataset.student));return}if(a.dataset.contract){navigate("contract",Number(a.dataset.contract));return}if(a.dataset.go){navigate(a.dataset.go);return}});
document.addEventListener("input",function(e){if(e.target.id==="students-filter"||e.target.id==="group-filter")applyStudentsFilter()});
document.addEventListener("keydown",function(e){if(e.key==="Enter"&&e.target.id==="top-search"){e.preventDefault();var q=e.target.value;navigate("students");var f=el("students-filter");if(f){f.value=q;applyStudentsFilter();f.focus()}}});
document.addEventListener("change",function(e){if(e.target.id==="group-filter")applyStudentsFilter();if(e.target.id==="profile-upload")uploadPhoto(e.target.files[0])});
window.addEventListener("hashchange",syncHash);
applyTheme();render();
})();
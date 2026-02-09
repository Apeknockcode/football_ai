use base64::Engine;
use chrono::Datelike;
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::Command;
use std::sync::mpsc;
use tauri::{AppHandle, WebviewUrl, WebviewWindowBuilder};

#[derive(Serialize)]
pub struct RunResult {
    pub stdout: String,
    pub stderr: String,
    pub code: i32,
}

fn project_root_from_cwd() -> PathBuf {
    std::env::current_dir()
        .ok()
        .and_then(|p| {
            let name = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if name == "src-tauri" {
                // 从 desktop/src-tauri 运行时，项目根是上两级
                p.parent().and_then(|desktop| desktop.parent().map(|root| root.to_path_buf()))
            } else if name == "desktop" {
                p.parent().map(|root| root.to_path_buf())
            } else {
                Some(p)
            }
        })
        .unwrap_or_else(|| PathBuf::from("."))
}

fn resolve_project_root(project_root: Option<String>) -> PathBuf {
    if let Some(s) = project_root {
        let t = s.trim();
        if !t.is_empty() {
            return PathBuf::from(t);
        }
    }
    project_root_from_cwd()
}

#[allow(dead_code)]
const SCRAPE_PORT_START: u16 = 38473;
#[allow(dead_code)]
const SCRAPE_PORT_END: u16 = 38482;

#[allow(dead_code)]
fn understat_matches_to_csv(
    root: &std::path::Path,
    league: &str,
    season: u32,
    matches: &[serde_json::Value],
) -> Result<usize, String> {
    if matches.is_empty() {
        return Ok(0);
    }
    let mut list: Vec<(chrono::NaiveDateTime, serde_json::Value)> = Vec::new();
    let default_dt = chrono::NaiveDateTime::MIN;
    for m in matches {
        let dt_str = m.get("datetime").or_else(|| m.get("date"));
        let dt = dt_str
            .and_then(|v| v.as_str())
            .and_then(|s| {
                chrono::NaiveDateTime::parse_from_str(s.get(..19)?, "%Y-%m-%d %H:%M:%S").ok()
            })
            .unwrap_or(default_dt);
        list.push((dt, m.clone()));
    }
    list.sort_by_key(|(dt, _)| *dt);
    let mut round = 1i32;
    let mut count = 0i32;
    for (_, m) in list.iter_mut() {
        if let Some(obj) = m.as_object_mut() {
            obj.insert("_round".to_string(), serde_json::json!(round));
        }
        count += 1;
        if count >= 10 {
            count = 0;
            round += 1;
        }
    }
    let hist_dir = root.join("data").join("historical").join(league);
    std::fs::create_dir_all(&hist_dir).map_err(|e| format!("创建目录失败: {}", e))?;
    let out_path = hist_dir.join(format!("pl_{}.csv", season));
    let mut w = csv::Writer::from_path(&out_path).map_err(|e| format!("写 CSV 失败: {}", e))?;
    w.write_record([
        "season",
        "round",
        "home_team",
        "away_team",
        "xg_home",
        "xg_away",
        "goals_home",
        "goals_away",
    ])
    .map_err(|e| format!("写表头失败: {}", e))?;
    let mut n = 0usize;
    for (_, m) in list {
        let h = m.get("h");
        let a = m.get("a");
        let goals = m.get("goals").and_then(|v| v.as_object());
        let xg = m.get("xG").and_then(|v| v.as_object());
        let home_team = team_name(h);
        let away_team = team_name(a);
        let (goals_h, goals_a) = if let Some(g) = goals {
            (
                g.get("h").and_then(|v| v.as_f64()).unwrap_or(0.0) as i32,
                g.get("a").and_then(|v| v.as_f64()).unwrap_or(0.0) as i32,
            )
        } else {
            (0, 0)
        };
        let (xg_h, xg_a) = if let Some(x) = xg {
            (
                x.get("h").and_then(|v| v.as_f64()).unwrap_or(0.0),
                x.get("a").and_then(|v| v.as_f64()).unwrap_or(0.0),
            )
        } else {
            (0.0, 0.0)
        };
        let r = m.get("_round").and_then(|v| v.as_i64()).unwrap_or(0);
        w.write_record([
            season.to_string(),
            r.to_string(),
            home_team,
            away_team,
            format!("{:.4}", xg_h),
            format!("{:.4}", xg_a),
            goals_h.to_string(),
            goals_a.to_string(),
        ])
        .map_err(|e| format!("写行失败: {}", e))?;
        n += 1;
    }
    w.flush().map_err(|e| format!("flush CSV 失败: {}", e))?;
    Ok(n)
}

#[allow(dead_code)]
fn team_name(v: Option<&serde_json::Value>) -> String {
    let v = match v {
        Some(x) => x,
        None => return "Unknown".to_string(),
    };
    if let Some(obj) = v.as_object() {
        let s = obj
            .get("title")
            .or_else(|| obj.get("short_title"))
            .and_then(|x| x.as_str())
            .unwrap_or("")
            .trim();
        if s.is_empty() {
            "Unknown".to_string()
        } else {
            s.to_string()
        }
    } else {
        v.as_str().unwrap_or("").trim().to_string()
    }
}

#[allow(dead_code)]
fn run_scrape_server(
    root: PathBuf,
    tx: mpsc::Sender<(String, Result<usize, String>)>,
    tx_port: mpsc::Sender<Result<u16, String>>,
) {
    let mut last_err = String::new();
    let listener = (SCRAPE_PORT_START..=SCRAPE_PORT_END).find_map(|port| {
        match std::net::TcpListener::bind(("127.0.0.1", port)) {
            Ok(l) => {
                let _ = tx_port.send(Ok(port));
                Some((l, port))
            }
            Err(e) => {
                last_err = format!("{}: {}", port, e);
                None
            }
        }
    });
    let (listener, _port) = match listener {
        Some(x) => x,
        None => {
            let _ = tx_port.send(Err(format!("绑定端口 {}-{} 均失败，最后: {}", SCRAPE_PORT_START, SCRAPE_PORT_END, last_err)));
            return;
        }
    };
    for stream in listener.incoming().take(10) {
        let mut stream = match stream {
            Ok(s) => s,
            Err(_) => continue,
        };
        let mut buf = [0u8; 256 * 1024];
        let n = match stream.read(&mut buf) {
            Ok(0) => continue,
            Ok(n) => n,
            Err(_) => continue,
        };
        let req = String::from_utf8_lossy(&buf[..n]).into_owned();
        let root = root.clone();
        let tx = tx.clone();
        handle_one_request(&mut stream, &req, &root, tx);
    }
}

#[allow(dead_code)]
fn parse_request_line(req: &str) -> Option<(&str, &str, &str)> {
    let line = req.lines().next()?;
    let parts: Vec<&str> = line.splitn(3, ' ').collect();
    if parts.len() < 2 {
        return None;
    }
    let method = parts[0];
    let path_query = parts[1];
    let (path, query) = path_query.split_once('?').unwrap_or((path_query, ""));
    Some((method, path, query))
}

#[allow(dead_code)]
fn handle_one_request(
    stream: &mut std::net::TcpStream,
    req: &str,
    root: &PathBuf,
    tx: mpsc::Sender<(String, Result<usize, String>)>,
) {
    let (method, path, query) = match parse_request_line(req) {
        Some(x) => x,
        None => {
            send_http_response(stream, 400, "Bad Request");
            return;
        }
    };

    if method == "GET" && path.starts_with("/league/") {
        let rest = path.trim_start_matches("/league/").trim_end_matches('/');
        let segments: Vec<&str> = rest.splitn(2, '/').collect();
        if segments.len() != 2 {
            send_http_response(stream, 400, "Bad path: use /league/{league}/{season}");
            return;
        }
        let league = segments[0];
        let season = segments[1];
        let url = format!("https://understat.com/league/{}/{}", league, season);
        let client = match reqwest::blocking::Client::builder()
            .user_agent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            .danger_accept_invalid_certs(true)
            .build()
        {
            Ok(c) => c,
            Err(e) => {
                send_http_response(stream, 502, &format!("创建 HTTP 客户端失败: {}", e));
                return;
            }
        };
        let mut body = match client.get(&url).send() {
            Ok(r) if r.status().is_success() => match r.text() {
                Ok(t) => t,
                Err(e) => {
                    send_http_response(stream, 502, &format!("读取 Understat 响应失败: {}", e));
                    return;
                }
            },
            Ok(r) => {
                send_http_response(stream, 502, &format!("Understat 返回: {}", r.status()));
                return;
            }
            Err(e) => {
                send_http_response(stream, 502, &format!("请求 Understat 失败: {}", e));
                return;
            }
        };
        body.push_str("\n<script>\n");
        body.push_str(&understat_embed_script(league, season));
        body.push_str("\n</script>");
        send_http_response_with_type(stream, 200, "text/html; charset=utf-8", &body);
        return;
    }

    if method == "POST" && path.starts_with("/scrape") {
        let mut league = String::new();
        let mut season_str = String::new();
        for part in query.split('&').take(10) {
            let kv: Vec<&str> = part.splitn(2, '=').collect();
            if kv.len() == 2 {
                match kv[0] {
                    "league" => league = kv[1].to_string(),
                    "season" => season_str = kv[1].to_string(),
                    _ => {}
                }
            }
        }
        if league.is_empty() || season_str.is_empty() {
            send_http_response(stream, 400, "Missing league or season");
            return;
        }
        let season: u32 = match season_str.parse() {
            Ok(s) => s,
            Err(_) => {
                send_http_response(stream, 400, "Invalid season");
                return;
            }
        };
        let body_start = match req.find("\r\n\r\n") {
            Some(i) => i + 4,
            None => {
                send_http_response(stream, 400, "No body");
                return;
            }
        };
        let body = req[body_start..].trim();
        let matches: Vec<serde_json::Value> = match serde_json::from_str(body) {
            Ok(m) => m,
            Err(e) => {
                send_http_response(stream, 400, &format!("JSON 解析失败: {}", e));
                return;
            }
        };
        let result = understat_matches_to_csv(root, &league, season, &matches);
        let _ = tx.send((league.clone(), result.clone()));
        if result.is_ok() {
            send_http_response(stream, 200, "OK");
        } else {
            send_http_response(stream, 500, &result.unwrap_err());
        }
        return;
    }

    send_http_response(stream, 404, "Not Found");
}

#[allow(dead_code)]
fn send_http_response(stream: &mut std::net::TcpStream, code: u16, body: &str) {
    send_http_response_with_type(stream, code, "text/plain; charset=utf-8", body);
}

#[allow(dead_code)]
fn send_http_response_with_type(stream: &mut std::net::TcpStream, code: u16, content_type: &str, body: &str) {
    let status = match code {
        200 => "OK",
        400 => "Bad Request",
        404 => "Not Found",
        405 => "Method Not Allowed",
        500 => "Internal Server Error",
        502 => "Bad Gateway",
        _ => "Unknown",
    };
    let msg = format!(
        "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        code,
        status,
        content_type,
        body.len(),
        body
    );
    let _ = stream.write_all(msg.as_bytes());
    let _ = stream.flush();
}

#[allow(dead_code)]
fn understat_embed_script(league: &str, season: &str) -> String {
    let path = format!("/scrape?league={}&season={}", league, season);
    format!(
        r#"
window.addEventListener('load', function(){{
  var path = {:?};
  var scripts = document.querySelectorAll('script');
  var re = /(?:datesData|teamsData)\s*=\s*JSON\.parse\s*\(\s*'((?:[^'\\]|\\.)*)'\s*\)/;
  for (var i = 0; i < scripts.length; i++) {{
    var t = scripts[i].textContent || '';
    var m = t.match(re);
    if (m) {{
      var raw = m[1].replace(/\\'/g,"'").replace(/\\"/g,'"').replace(/\\\\/g,"\\");
      try {{
        var data = JSON.parse(raw);
        if (Array.isArray(data)) {{
          fetch(path, {{ method: 'POST', body: JSON.stringify(data), headers: {{ 'Content-Type': 'application/json' }} }}).catch(function(e) {{ console.error(e); }});
        }} else if (data && typeof data === 'object') {{
          var arr = [];
          for (var k in data) {{ if (Array.isArray(data[k])) arr = arr.concat(data[k]); }}
          if (arr.length) fetch(path, {{ method: 'POST', body: JSON.stringify(arr), headers: {{ 'Content-Type': 'application/json' }} }}).catch(function(e) {{ console.error(e); }});
        }}
      }} catch(e) {{ console.error(e); }}
      break;
    }}
  }}
}});
"#,
        path
    )
}

fn get_python(root: &std::path::Path) -> PathBuf {
    let venv = root.join(".venv").join("bin").join("python");
    if venv.exists() {
        return venv;
    }
    PathBuf::from("python3")
}

/// 在 macOS 上若使用项目 .venv，则用 `arch -arm64` 启动 Python，使与 arm64 的 numpy/pandas 一致，避免架构不匹配。
fn new_python_cmd(root: &std::path::Path) -> Command {
    let python = get_python(root);
    let is_venv = python.to_string_lossy().contains(".venv");
    if cfg!(target_os = "macos") && is_venv {
        let mut cmd = Command::new("arch");
        cmd.arg("-arm64").arg(&python);
        cmd
    } else {
        let cmd = Command::new(&python);
        cmd
    }
}

#[tauri::command]
fn get_project_root_suggestion() -> String {
    project_root_from_cwd().display().to_string()
}

/// 表格中的一场比赛，用于写入 todays_matches.csv 后运行预测
#[derive(Debug, Deserialize)]
struct PredictMatchRow {
    home_team: String,
    away_team: String,
    #[serde(default)]
    round: Option<u32>,
    #[serde(default)]
    league_id: Option<String>,
    #[serde(default)]
    league_zh: Option<String>,
    #[serde(default)]
    handicap_note: Option<String>,
    #[serde(default)]
    xg_home: Option<String>,
    #[serde(default)]
    xg_away: Option<String>,
    #[serde(default)]
    match_id: Option<String>,
}

fn run_predict_impl(
    root: &std::path::Path,
    date_dir: &std::path::Path,
    csv_path: &std::path::Path,
    model: Option<&str>,
) -> RunResult {
    let out_path = date_dir.join("todays_predictions.csv");
    let injuries_dir = date_dir.join("todays_injuries");
    let expected_xg = root.join("data").join("expected_xg_teams.csv");
    let script = root.join("scripts").join("predict_batch.py");

    if !script.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("脚本不存在: {}", script.display()),
            code: 1,
        };
    }

    let mut cmd = new_python_cmd(root);
    cmd.current_dir(root)
        .arg(&script)
        .arg(csv_path)
        .arg("--expected-xg")
        .arg(&expected_xg)
        .arg("--out")
        .arg(&out_path)
        .arg("--injuries-dir")
        .arg(&injuries_dir);

    let model_str = model.map(|s| s.trim()).filter(|s| !s.is_empty());
    if let Some(m) = model_str {
        if m == "ml" || m == "ensemble" {
            cmd.arg("--model").arg(m);
            let hist_dir = root.join("data").join("historical");
            if hist_dir.exists() {
                cmd.arg("--historical").arg(&hist_dir);
                let season = chrono::Utc::now().year();
                cmd.arg("--season").arg(season.to_string());
            }
        }
    }

    let output = cmd.output();
    match output {
        Ok(o) => RunResult {
            stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
            code: o.status.code().unwrap_or(-1),
        },
        Err(e) => RunResult {
            stdout: String::new(),
            stderr: format!("执行失败: {}", e),
            code: -1,
        },
    }
}

#[tauri::command]
fn run_predict_today(
    project_root: Option<String>,
    date: String,
    model: Option<String>,
) -> RunResult {
    let root = resolve_project_root(project_root);
    let date = date.trim().to_string();
    let date_dir = root.join("data").join(&date);
    let _ = std::fs::create_dir_all(&date_dir);
    let _ = std::fs::create_dir_all(date_dir.join("todays_injuries"));
    let csv_path = date_dir.join("todays_matches.csv");
    run_predict_impl(&root, &date_dir, &csv_path, model.as_deref())
}

/// 从表格数据写入 todays_matches.csv 后运行预测（逐场在脚本内批量执行）
#[tauri::command]
fn run_predict_today_with_matches(
    project_root: Option<String>,
    date: String,
    matches: Vec<PredictMatchRow>,
    model: Option<String>,
) -> RunResult {
    let root = resolve_project_root(project_root);
    let date = date.trim().to_string();
    if date.is_empty() {
        return RunResult {
            stdout: String::new(),
            stderr: "请选择日期".to_string(),
            code: 1,
        };
    }
    let valid: Vec<_> = matches
        .into_iter()
        .filter(|m| {
            let h = m.home_team.trim();
            let a = m.away_team.trim();
            !h.is_empty() && !a.is_empty()
        })
        .collect();
    if valid.is_empty() {
        return RunResult {
            stdout: String::new(),
            stderr: "表格中至少需填写一场比赛（主队、客队）".to_string(),
            code: 1,
        };
    }

    let date_dir = root.join("data").join(&date);
    let _ = std::fs::create_dir_all(&date_dir);
    let _ = std::fs::create_dir_all(date_dir.join("todays_injuries"));
    let csv_path = date_dir.join("todays_matches.csv");

    let mut w = match csv::Writer::from_path(&csv_path) {
        Ok(w) => w,
        Err(e) => {
            return RunResult {
                stdout: String::new(),
                stderr: format!("写入 CSV 失败: {}", e),
                code: 1,
            };
        }
    };
    let headers = [
        "match_id",
        "league_id",
        "league_zh",
        "home_team",
        "away_team",
        "round",
        "handicap_note",
        "xg_home",
        "xg_away",
    ];
    if w.write_record(&headers).is_err() {
        return RunResult {
            stdout: String::new(),
            stderr: "写表头失败".to_string(),
            code: 1,
        };
    }
    for (i, m) in valid.iter().enumerate() {
        let match_id = m.match_id.as_deref().unwrap_or("").to_string();
        let league_id = m.league_id.as_deref().unwrap_or("EPL").trim().to_string();
        let league_zh = m.league_zh.as_deref().unwrap_or("").to_string();
        let home = m.home_team.trim().to_string();
        let away = m.away_team.trim().to_string();
        let round = m.round.unwrap_or(1);
        let handicap = m.handicap_note.as_deref().unwrap_or("").to_string();
        let xg_h = m.xg_home.as_deref().unwrap_or("").to_string();
        let xg_a = m.xg_away.as_deref().unwrap_or("").to_string();
        let record = [
            if match_id.is_empty() {
                format!("{:03}", i + 1)
            } else {
                match_id
            },
            league_id,
            league_zh,
            home,
            away,
            round.to_string(),
            handicap,
            xg_h,
            xg_a,
        ];
        if w.write_record(&record).is_err() {
            return RunResult {
                stdout: String::new(),
                stderr: format!("写第 {} 行失败", i + 1),
                code: 1,
            };
        }
    }
    drop(w);
    run_predict_impl(&root, &date_dir, &csv_path, model.as_deref())
}

#[tauri::command]
fn save_prediction_images(
    project_root: Option<String>,
    date: String,
    match_list_base64: Option<String>,
    injury_base64: Option<String>,
) -> Result<String, String> {
    let root = resolve_project_root(project_root);
    let date = date.trim();
    if date.is_empty() {
        return Err("请先选择日期".to_string());
    }
    let dir = root.join("data").join(date).join("todays_injuries");
    std::fs::create_dir_all(&dir).map_err(|e| format!("创建目录失败: {}", e))?;
    let mut saved = Vec::new();
    if let Some(b64) = match_list_base64 {
        let b64 = b64.trim().replace('\n', "").replace('\r', "");
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(&b64)
            .map_err(|e| format!("比赛列表图片解码失败: {}", e))?;
        let path = dir.join("match_list.png");
        std::fs::write(&path, &bytes).map_err(|e| format!("写入失败: {}", e))?;
        saved.push(path.display().to_string());
    }
    if let Some(b64) = injury_base64 {
        let b64 = b64.trim().replace('\n', "").replace('\r', "");
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(&b64)
            .map_err(|e| format!("伤停图片解码失败: {}", e))?;
        let path = dir.join("injury.png");
        std::fs::write(&path, &bytes).map_err(|e| format!("写入失败: {}", e))?;
        saved.push(path.display().to_string());
    }
    if saved.is_empty() {
        return Err("请至少上传一张图片（比赛列表或伤停）".to_string());
    }
    Ok(format!("已保存 {} 张图片到 data/{}/todays_injuries/", saved.len(), date))
}

#[tauri::command]
async fn run_ocr_todays_images(project_root: Option<String>, date: String) -> RunResult {
    let root = resolve_project_root(project_root);
    let date = date.trim().to_string();
    if date.is_empty() {
        return RunResult {
            stdout: String::new(),
            stderr: "请先选择日期".to_string(),
            code: 1,
        };
    }
    let dir = root.join("data").join(&date).join("todays_injuries");
    let script = root.join("scripts").join("parse_injury_images.py");
    if !script.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("脚本不存在: {}", script.display()),
            code: 1,
        };
    }
    let result = tauri::async_runtime::spawn_blocking(move || {
        let output = new_python_cmd(&root)
            .current_dir(&root)
            .arg(&script)
            .arg("--dir")
            .arg(&dir)
            .arg("--quiet")
            .output();
        match output {
            Ok(o) => RunResult {
                stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
                stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
                code: o.status.code().unwrap_or(-1),
            },
            Err(e) => RunResult {
                stdout: String::new(),
                stderr: format!("执行失败: {}", e),
                code: -1,
            },
        }
    })
    .await;
    result.unwrap_or_else(|e| RunResult {
        stdout: String::new(),
        stderr: format!("任务异常: {}", e),
        code: -1,
    })
}

#[tauri::command]
fn read_predictions_csv(project_root: Option<String>, date: String) -> Result<String, String> {
    let root = resolve_project_root(project_root);
    let path = root.join("data").join(date.trim()).join("todays_predictions.csv");
    std::fs::read_to_string(&path).map_err(|e| format!("{}: {}", path.display(), e))
}

#[tauri::command]
fn read_todays_matches_csv(project_root: Option<String>, date: String) -> Result<String, String> {
    let root = resolve_project_root(project_root);
    let path = root.join("data").join(date.trim()).join("todays_matches.csv");
    std::fs::read_to_string(&path).map_err(|e| format!("{}: {}", path.display(), e))
}

/// 获取指定日期的五大联赛赛程（ESPN API），写入 data/<日期>/todays_matches.csv
#[tauri::command]
fn fetch_todays_fixtures(project_root: Option<String>, date: String) -> RunResult {
    let root = resolve_project_root(project_root);
    let date = date.trim().to_string();
    if date.is_empty() {
        return RunResult {
            stdout: String::new(),
            stderr: "请选择日期".to_string(),
            code: 1,
        };
    }
    let script = root.join("scripts").join("fetch_todays_fixtures.py");
    if !script.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("脚本不存在: {}", script.display()),
            code: 1,
        };
    }
    let output = new_python_cmd(&root)
        .current_dir(&root)
        .arg(&script)
        .arg("--date")
        .arg(&date)
        .output();
    match output {
        Ok(o) => RunResult {
            stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
            code: o.status.code().unwrap_or(-1),
        },
        Err(e) => RunResult {
            stdout: String::new(),
            stderr: format!("执行失败: {}", e),
            code: -1,
        },
    }
}

/// 从 The Odds API 拉取盘口并合并到 data/<日期>/todays_matches.csv（需设置环境变量 THE_ODDS_API_KEY）
#[tauri::command]
fn fetch_odds(project_root: Option<String>, date: String) -> RunResult {
    let root = resolve_project_root(project_root);
    let date = date.trim().to_string();
    if date.is_empty() {
        return RunResult {
            stdout: String::new(),
            stderr: "请选择日期".to_string(),
            code: 1,
        };
    }
    let script = root.join("scripts").join("fetch_odds.py");
    if !script.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("脚本不存在: {}", script.display()),
            code: 1,
        };
    }
    let csv_path = root.join("data").join(&date).join("todays_matches.csv");
    if !csv_path.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("赛程文件不存在: {}，请先「获取今日五大联赛」", csv_path.display()),
            code: 1,
        };
    }
    let output = new_python_cmd(&root)
        .current_dir(&root)
        .arg(&script)
        .arg("--csv")
        .arg(&csv_path)
        .output();
    match output {
        Ok(o) => RunResult {
            stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
            code: o.status.code().unwrap_or(-1),
        },
        Err(e) => RunResult {
            stdout: String::new(),
            stderr: format!("执行失败: {}", e),
            code: -1,
        },
    }
}

#[tauri::command]
fn run_pre_report(
    project_root: Option<String>,
    home: String,
    away: String,
    round: i32,
    league: Option<String>,
    season: Option<i32>,
) -> RunResult {
    let root = resolve_project_root(project_root);
    let mut cmd = new_python_cmd(&root);
    cmd.current_dir(&root)
        .arg("-m")
        .arg("football_ai.cli")
        .arg("pre")
        .arg("--home")
        .arg(home.trim())
        .arg("--away")
        .arg(away.trim())
        .arg("--round")
        .arg(round.to_string());
    if let Some(ref league_id) = league {
        if !league_id.is_empty() {
            cmd.arg("--league").arg(league_id);
            let hist_dir = root.join("data").join("historical").join(league_id);
            if hist_dir.exists() {
                cmd.arg("--historical").arg(hist_dir.to_string_lossy().as_ref());
            }
        }
    }
    if let Some(season_year) = season {
        if season_year >= 2020 && season_year <= 2030 {
            cmd.arg("--season").arg(season_year.to_string());
        }
    }

    let output = cmd.output();
    match output {
        Ok(o) => RunResult {
            stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
            code: o.status.code().unwrap_or(-1),
        },
        Err(e) => RunResult {
            stdout: String::new(),
            stderr: format!("执行失败: {}", e),
            code: -1,
        },
    }
}

#[tauri::command]
fn run_post_report(
    project_root: Option<String>,
    home: String,
    away: String,
    round: i32,
) -> RunResult {
    let root = resolve_project_root(project_root);
    let mut cmd = new_python_cmd(&root);
    cmd.current_dir(&root)
        .arg("-m")
        .arg("football_ai.cli")
        .arg("post")
        .arg("--home")
        .arg(home.trim())
        .arg("--away")
        .arg(away.trim())
        .arg("--round")
        .arg(round.to_string());

    let output = cmd.output();
    match output {
        Ok(o) => RunResult {
            stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
            code: o.status.code().unwrap_or(-1),
        },
        Err(e) => RunResult {
            stdout: String::new(),
            stderr: format!("执行失败: {}", e),
            code: -1,
        },
    }
}

#[tauri::command]
fn open_browser_window(app: AppHandle, url_input: String) -> Result<(), String> {
    let url_input = url_input.trim();
    if url_input.is_empty() {
        return Err("请填写要打开的网址".to_string());
    }
    let parsed = url_input
        .parse::<url::Url>()
        .map_err(|e| format!("网址无效: {}", e))?;
    let label = format!(
        "browser-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_millis()
    );
    WebviewWindowBuilder::new(&app, &label, WebviewUrl::External(parsed))
        .title("数据源 · 内置浏览器")
        .inner_size(900.0, 700.0)
        .build()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
async fn run_validate_data(
    project_root: Option<String>,
    mode: Option<String>,
    use_ref: Option<bool>,
) -> RunResult {
    let root = resolve_project_root(project_root);
    let script = root.join("scripts").join("validate_historical_data.py");
    if !script.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("脚本不存在: {}", script.display()),
            code: 1,
        };
    }
    let mode = mode.unwrap_or_default();
    let use_ref = use_ref.unwrap_or(false);
    let result = tauri::async_runtime::spawn_blocking(move || {
        let mut cmd = new_python_cmd(&root);
        cmd.current_dir(&root).arg(&script);
        match mode.as_str() {
            "2024" => {
                cmd.arg("--merged-2024");
                if use_ref {
                    cmd.arg("--ref");
                }
            }
            "2025" => {
                cmd.arg("--merged-2025");
                if use_ref {
                    cmd.arg("--ref");
                }
            }
            "2026" => {
                cmd.arg("--merged-2026");
                if use_ref {
                    cmd.arg("--ref");
                }
            }
            _ => {}
        }
        let output = cmd.output();
        match output {
            Ok(o) => RunResult {
                stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
                stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
                code: o.status.code().unwrap_or(-1),
            },
            Err(e) => RunResult {
                stdout: String::new(),
                stderr: format!("执行失败: {}", e),
                code: -1,
            },
        }
    })
    .await;
    result.unwrap_or_else(|e| RunResult {
        stdout: String::new(),
        stderr: format!("任务异常: {}", e),
        code: -1,
    })
}

const FIVE_LEAGUES: [&str; 5] = ["EPL", "La_Liga", "Bundesliga", "Serie_A", "Ligue_1"];

#[tauri::command]
async fn run_fetch_five_leagues(project_root: Option<String>, year: String) -> RunResult {
    let root = resolve_project_root(project_root);
    let script = root.join("scripts").join("fetch_historical_understat.py");
    if !script.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("脚本不存在: {}", script.display()),
            code: 1,
        };
    }
    let year = year.trim().to_string();
    if year.is_empty() {
        return RunResult {
            stdout: String::new(),
            stderr: "请填写年份（如 2026）".to_string(),
            code: 1,
        };
    }
    let result = tauri::async_runtime::spawn_blocking(move || {
        let mut all_out = String::new();
        let mut all_err = String::new();
        let mut last_code = 0i32;
        for league in FIVE_LEAGUES {
            all_out.push_str(&format!("\n--- {} ---\n", league));
            let output = new_python_cmd(&root)
                .current_dir(&root)
                .arg(&script)
                .arg("--league")
                .arg(league)
                .arg("--season")
                .arg(&year)
                .output();
            match output {
                Ok(o) => {
                    let so = String::from_utf8_lossy(&o.stdout);
                    let se = String::from_utf8_lossy(&o.stderr);
                    all_out.push_str(&so);
                    if !se.is_empty() {
                        all_err.push_str(&format!("[{}] ", league));
                        all_err.push_str(&se);
                    }
                    last_code = o.status.code().unwrap_or(-1);
                }
                Err(e) => {
                    all_err.push_str(&format!("[{}] 执行失败: {}\n", league, e));
                    last_code = -1;
                }
            }
        }
        all_out.push_str("\n一键拉取完成。");
        RunResult {
            stdout: all_out.trim_start().to_string(),
            stderr: all_err,
            code: last_code,
        }
    })
    .await;
    result.unwrap_or_else(|e| RunResult {
        stdout: String::new(),
        stderr: format!("任务异常: {}", e),
        code: -1,
    })
}

#[tauri::command]
async fn run_calibrate(project_root: Option<String>, league: Option<String>) -> RunResult {
    let root = resolve_project_root(project_root);
    let script = root.join("scripts").join("calibrate_pl.py");
    if !script.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("脚本不存在: {}", script.display()),
            code: 1,
        };
    }
    let league_arg = league.as_deref().unwrap_or("Combined").trim();
    let league_arg = if league_arg.is_empty() {
        "Combined".to_string()
    } else {
        league_arg.to_string()
    };
    let result = tauri::async_runtime::spawn_blocking(move || {
        let output = new_python_cmd(&root)
            .current_dir(&root)
            .arg(&script)
            .arg("--league")
            .arg(&league_arg)
            .output();
        match output {
            Ok(o) => RunResult {
                stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
                stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
                code: o.status.code().unwrap_or(-1),
            },
            Err(e) => RunResult {
                stdout: String::new(),
                stderr: format!("执行失败: {}", e),
                code: -1,
            },
        }
    })
    .await;
    result.unwrap_or_else(|e| RunResult {
        stdout: String::new(),
        stderr: format!("任务异常: {}", e),
        code: -1,
    })
}

#[tauri::command]
async fn run_merge_five_leagues(project_root: Option<String>) -> RunResult {
    let root = resolve_project_root(project_root);
    let script = root.join("scripts").join("merge_five_leagues.py");
    if !script.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("脚本不存在: {}", script.display()),
            code: 1,
        };
    }
    let result = tauri::async_runtime::spawn_blocking(move || {
        let output = new_python_cmd(&root).current_dir(&root).arg(&script).output();
        match output {
            Ok(o) => RunResult {
                stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
                stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
                code: o.status.code().unwrap_or(-1),
            },
            Err(e) => RunResult {
                stdout: String::new(),
                stderr: format!("执行失败: {}", e),
                code: -1,
            },
        }
    })
    .await;
    result.unwrap_or_else(|e| RunResult {
        stdout: String::new(),
        stderr: format!("任务异常: {}", e),
        code: -1,
    })
}

#[tauri::command]
async fn run_backtest(project_root: Option<String>, league: Option<String>) -> RunResult {
    let root = resolve_project_root(project_root);
    let script = root.join("scripts").join("backtest_pl.py");
    if !script.exists() {
        return RunResult {
            stdout: String::new(),
            stderr: format!("脚本不存在: {}", script.display()),
            code: 1,
        };
    }
    let league_arg = league.as_deref().unwrap_or("Combined").trim();
    let league_arg = if league_arg.is_empty() {
        "Combined".to_string()
    } else {
        league_arg.to_string()
    };
    let result = tauri::async_runtime::spawn_blocking(move || {
        let output = new_python_cmd(&root)
            .current_dir(&root)
            .arg(&script)
            .arg("--league")
            .arg(&league_arg)
            .output();
        match output {
            Ok(o) => RunResult {
                stdout: String::from_utf8_lossy(&o.stdout).into_owned(),
                stderr: String::from_utf8_lossy(&o.stderr).into_owned(),
                code: o.status.code().unwrap_or(-1),
            },
            Err(e) => RunResult {
                stdout: String::new(),
                stderr: format!("执行失败: {}", e),
                code: -1,
            },
        }
    })
    .await;
    result.unwrap_or_else(|e| RunResult {
        stdout: String::new(),
        stderr: format!("任务异常: {}", e),
        code: -1,
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            get_project_root_suggestion,
            run_predict_today,
            run_predict_today_with_matches,
            save_prediction_images,
            run_ocr_todays_images,
            read_predictions_csv,
            read_todays_matches_csv,
            fetch_todays_fixtures,
            fetch_odds,
            run_pre_report,
            run_post_report,
            open_browser_window,
            run_validate_data,
            run_fetch_five_leagues,
            run_merge_five_leagues,
            run_calibrate,
            run_backtest,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

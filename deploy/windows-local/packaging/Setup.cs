// SEO Brain Setup - self-extracting installer stub.
// Layout of the final EXE:  [this stub][payload.zip][Int64 payload length][8 bytes magic "SBSETUP1"]
// The stub unpacks the ZIP into the chosen folder, runs installer\install.ps1 (offline: bundled Python wheels, bundled
// Node.js, prebuilt web UI), registers an uninstall entry for the current user and offers to launch the app.
// Compiled with the .NET Framework C# 5 compiler that ships with Windows (no SDK needed) - keep the syntax C# 5.
//
//   SEO-Brain-Setup.exe                                   wizard
//   SEO-Brain-Setup.exe /silent /dir=D:\SEO-Brain         unattended (also: /noshortcut /nolaunch /noregistry)
//   SEO-Brain-Setup.exe /autostart /dir=...               wizard that presses "install" by itself (UI tests)
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("SEO Brain Setup")]
[assembly: AssemblyProduct("SEO Brain")]
[assembly: AssemblyDescription("SEO Brain - local SEO operating system (offline installer)")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace SeoBrainSetup
{
    sealed class Options
    {
        public bool Silent, NoLaunch, NoShortcut, NoRegistry, AutoStart;
        public string Dir;
    }

    /// <summary>Read-only seekable window over a part of a file (the ZIP appended to this EXE).</summary>
    sealed class SubStream : Stream
    {
        readonly FileStream _f; readonly long _start, _length; long _pos;
        public SubStream(FileStream f, long start, long length) { _f = f; _start = start; _length = length; }
        public override bool CanRead { get { return true; } }
        public override bool CanSeek { get { return true; } }
        public override bool CanWrite { get { return false; } }
        public override long Length { get { return _length; } }
        public override long Position { get { return _pos; } set { _pos = value; } }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count)
        {
            long left = _length - _pos;
            if (left <= 0) return 0;
            if (count > left) count = (int)left;
            _f.Position = _start + _pos;
            int n = _f.Read(buffer, offset, count);
            _pos += n;
            return n;
        }
        public override long Seek(long offset, SeekOrigin origin)
        {
            if (origin == SeekOrigin.Begin) _pos = offset;
            else if (origin == SeekOrigin.Current) _pos += offset;
            else _pos = _length + offset;
            return _pos;
        }
        public override void SetLength(long value) { throw new NotSupportedException(); }
        public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
    }

    static class Core
    {
        public const string Magic = "SBSETUP1";
        public const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\SEO-Brain";

        public static string DefaultDir()
        {
            foreach (string letter in new[] { "D", "E", "C" })
            {
                try
                {
                    DriveInfo d = new DriveInfo(letter);
                    if (d.IsReady && d.DriveType == DriveType.Fixed && d.AvailableFreeSpace > 2L * 1024 * 1024 * 1024) return letter + @":\SEO-Brain";
                }
                catch { }
            }
            return @"C:\SEO-Brain";
        }

        public static bool IsAscii(string s) { foreach (char c in s) if (c > 127) return false; return true; }

        static void RunPs(string script, string args, string workDir, Action<string> log)
        {
            ProcessStartInfo psi = new ProcessStartInfo("powershell.exe", "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\" " + args);
            psi.WorkingDirectory = workDir; psi.UseShellExecute = false; psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true; psi.RedirectStandardError = true;
            using (Process p = new Process())
            {
                p.StartInfo = psi;
                p.OutputDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) log(e.Data); };
                p.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) log(e.Data); };
                p.Start(); p.BeginOutputReadLine(); p.BeginErrorReadLine(); p.WaitForExit();
                LastExitCode = p.ExitCode;
            }
        }
        public static int LastExitCode;

        /// <summary>Unpack the payload. Existing user data (data\, .env) is never overwritten.</summary>
        public static void Extract(string dir, Action<int, int, string> progress, Action<string> log)
        {
            string exe = Assembly.GetExecutingAssembly().Location;
            Directory.CreateDirectory(dir);
            string root = Path.GetFullPath(dir).TrimEnd('\\') + "\\";
            string stop = Path.Combine(dir, @"installer\stop.ps1");
            if (File.Exists(stop)) { log("Stopping a running copy (if any)..."); try { RunPs(stop, "", dir, log); } catch { } }
            using (FileStream f = new FileStream(exe, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (f.Length < 16) throw new InvalidDataException("no payload");
                byte[] tail = new byte[16];
                f.Position = f.Length - 16; f.Read(tail, 0, 16);
                if (Encoding.ASCII.GetString(tail, 8, 8) != Magic) throw new InvalidDataException("This setup file is incomplete or damaged (payload marker missing). Download it again.");
                long len = BitConverter.ToInt64(tail, 0);
                long start = f.Length - 16 - len;
                if (len <= 0 || start <= 0) throw new InvalidDataException("This setup file is damaged (bad payload size).");
                using (ZipArchive zip = new ZipArchive(new SubStream(f, start, len), ZipArchiveMode.Read))
                {
                    int total = zip.Entries.Count, i = 0;
                    foreach (ZipArchiveEntry e in zip.Entries)
                    {
                        i++;
                        string rel = e.FullName.Replace('/', '\\');
                        string target = Path.GetFullPath(Path.Combine(dir, rel));
                        if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase)) continue;          // zip-slip guard
                        if (rel.EndsWith("\\") || e.Name.Length == 0) { Directory.CreateDirectory(target); continue; }
                        string low = rel.ToLowerInvariant();
                        if ((low.StartsWith("data\\") || low == ".env") && File.Exists(target)) continue;      // keep user data
                        Directory.CreateDirectory(Path.GetDirectoryName(target));
                        using (Stream src = e.Open())
                        using (FileStream dst = new FileStream(target, FileMode.Create, FileAccess.Write, FileShare.None))
                            src.CopyTo(dst, 1 << 20);
                        try { File.SetLastWriteTime(target, e.LastWriteTime.DateTime); } catch { }
                        if ((i & 63) == 0 || i == total) progress(i, total, rel);
                    }
                }
            }
        }

        public static int RunInstall(string dir, bool noShortcut, Action<string> log)
        {
            RunPs(Path.Combine(dir, @"installer\install.ps1"), noShortcut ? "-NoShortcut" : "", dir, log);
            return LastExitCode;
        }

        public static void Register(string dir)
        {
            using (RegistryKey k = Registry.CurrentUser.CreateSubKey(UninstallKey))
            {
                string version = "1.0";
                try { string vf = Path.Combine(dir, "VERSION.txt"); if (File.Exists(vf)) version = File.ReadAllLines(vf)[0].Trim(); } catch { }
                k.SetValue("DisplayName", "SEO Brain");
                k.SetValue("DisplayVersion", version);
                k.SetValue("Publisher", "SEO Brain");
                k.SetValue("InstallLocation", dir);
                k.SetValue("UninstallString", "\"" + Path.Combine(dir, "UNINSTALL.bat") + "\"");
                string ico = Path.Combine(dir, @"installer\seo-brain.ico");
                if (File.Exists(ico)) k.SetValue("DisplayIcon", ico);
                k.SetValue("NoModify", 1, RegistryValueKind.DWord);
                k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            }
        }

        public static void Launch(string dir)
        {
            ProcessStartInfo psi = new ProcessStartInfo(Path.Combine(dir, "START.bat"));
            psi.WorkingDirectory = dir; psi.UseShellExecute = true;
            Process.Start(psi);
        }
    }

    sealed class Wizard : Form
    {
        readonly Options _o;
        readonly Panel _pageStart = new Panel(), _pageWork = new Panel();
        readonly TextBox _dir = new TextBox(), _log = new TextBox();
        readonly CheckBox _shortcut = new CheckBox(), _launch = new CheckBox();
        readonly Button _install = new Button(), _close = new Button(), _browse = new Button();
        readonly ProgressBar _bar = new ProgressBar();
        readonly TextBox _status = Para("در حال آماده‌سازی…", Color.Black);
        readonly StringBuilder _sb = new StringBuilder();
        bool _busy, _done;

        public Wizard(Options o)
        {
            _o = o;
            SuspendLayout();
            AutoScaleDimensions = new SizeF(96F, 96F); AutoScaleMode = AutoScaleMode.Dpi;      // bounds below are 96-dpi pixels; WinForms scales them on 125 % / 150 % displays
            Text = "نصب SEO Brain"; ClientSize = new Size(640, 470); StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
            Font = new Font("Segoe UI", 9.75f); RightToLeft = RightToLeft.Yes; RightToLeftLayout = true;
            try { Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location); } catch { }

            Label head = new Label();
            head.Text = "SEO Brain"; head.Font = new Font("Segoe UI", 18f, FontStyle.Bold); head.ForeColor = Color.FromArgb(88, 80, 236);
            head.SetBounds(20, 14, 600, 40);
            Controls.Add(head);

            // ---- page 1
            _pageStart.SetBounds(0, 60, 640, 350);
            // read-only multi-line TextBoxes (not Labels): the Edit control wraps mixed Persian/Latin text reliably at any DPI
            TextBox intro = Para(
                "این برنامه SEO Brain را همراه با همهٔ پیش‌نیازها روی این سیستم نصب می‌کند و به اینترنت نیاز ندارد:\r\n" +
                "•  Python و Node.js همراه بسته هستند (اگر Python مناسب نباشد، بی‌صدا و بدون دسترسی ادمین نصب می‌شود).\r\n" +
                "•  همهٔ کتابخانه‌های بک‌اند و رابط وبِ ازپیش‌ساخته داخل همین فایل است.\r\n\r\n" +
                "بعد از نصب: تقویم محتوا ← «کلیدها» ← ردیف Gemini ← کلید رایگان Google AI Studio را بچسبانید و «تست» را بزنید.\r\n" +
                "اگر در ایران هستید قبل از اجرا VPN را روشن کنید؛ برنامه پروکسی آن را خودکار پیدا می‌کند.", Color.Black);
            intro.SetBounds(20, 6, 600, 152);
            TextBox l = Para("پوشهٔ نصب (مسیر انگلیسی و کوتاه بهتر است):", Color.Black); l.SetBounds(20, 164, 600, 24);
            _dir.SetBounds(120, 192, 500, 27); _dir.RightToLeft = RightToLeft.No; _dir.Text = o.Dir ?? Core.DefaultDir();
            _browse.Text = "انتخاب…"; _browse.SetBounds(20, 190, 92, 30); _browse.Click += delegate { Browse(); };
            _shortcut.Text = "ساخت میان‌بر روی دسکتاپ و منوی استارت"; _shortcut.Checked = !o.NoShortcut; _shortcut.SetBounds(20, 236, 600, 26);
            _launch.Text = "اجرای SEO Brain پس از پایان نصب"; _launch.Checked = !o.NoLaunch; _launch.SetBounds(20, 264, 600, 26);
            TextBox note = Para("فضای لازم: حدود ۱٫۵ گیگابایت. نصب روی نسخهٔ قبلی امن است؛ پوشهٔ data و فایل تنظیمات (env) شما دست‌نخورده می‌ماند.", Color.DimGray);
            note.SetBounds(20, 300, 600, 44);
            _pageStart.Controls.AddRange(new Control[] { l, _dir, _browse, _shortcut, _launch, note, intro });   // intro last = bottom of the z-order

            // ---- page 2
            _pageWork.SetBounds(0, 60, 640, 350); _pageWork.Visible = false;
            _status.SetBounds(20, 6, 600, 24); _status.Text = "در حال آماده‌سازی…";
            _bar.SetBounds(20, 34, 600, 20); _bar.RightToLeftLayout = true;
            _log.SetBounds(20, 64, 600, 280); _log.Multiline = true; _log.ReadOnly = true; _log.ScrollBars = ScrollBars.Vertical;
            _log.RightToLeft = RightToLeft.No; _log.Font = new Font("Consolas", 8.75f); _log.BackColor = Color.FromArgb(18, 18, 28); _log.ForeColor = Color.Gainsboro;
            _pageWork.Controls.AddRange(new Control[] { _status, _bar, _log });

            _install.Text = "نصب"; _install.SetBounds(20, 422, 120, 34); _install.Click += delegate { Start(); };
            _close.Text = "انصراف"; _close.SetBounds(150, 422, 120, 34); _close.Click += delegate { Close(); };
            AcceptButton = _install;
            Controls.AddRange(new Control[] { _pageStart, _pageWork, _install, _close });
            FormClosing += delegate(object s, FormClosingEventArgs e) { if (_busy) { e.Cancel = true; MessageBox.Show(this, "نصب در حال انجام است؛ لطفاً تا پایان صبر کنید.", Text); } };
            ResumeLayout(false); PerformLayout();
            if (o.AutoStart) Shown += delegate { Start(); };
        }

        static TextBox Para(string text, Color fore)
        {
            TextBox t = new TextBox();
            t.Multiline = true; t.ReadOnly = true; t.BorderStyle = BorderStyle.None; t.TabStop = false; t.Cursor = Cursors.Default;
            t.BackColor = SystemColors.Control; t.ForeColor = fore; t.Text = text;
            return t;
        }

        void Browse()
        {
            using (FolderBrowserDialog d = new FolderBrowserDialog())
            {
                d.Description = "پوشه‌ای که SEO Brain در آن نصب شود"; d.ShowNewFolderButton = true;
                if (d.ShowDialog(this) == DialogResult.OK) _dir.Text = Path.Combine(d.SelectedPath, "SEO-Brain");
            }
        }

        void Ui(MethodInvoker a) { if (IsDisposed) return; try { BeginInvoke(a); } catch { } }
        void Log(string line) { lock (_sb) _sb.AppendLine(line); Ui(delegate { _log.AppendText(line + "\r\n"); }); }

        void Start()
        {
            if (_done) { Close(); return; }
            string dir = _dir.Text.Trim();
            if (dir.Length < 4) { MessageBox.Show(this, "یک پوشهٔ معتبر انتخاب کنید.", Text); return; }
            if (!Core.IsAscii(dir) && MessageBox.Show(this, "مسیر حروف غیرانگلیسی دارد و ممکن است Python/Node با آن مشکل داشته باشند. ادامه می‌دهید؟", Text, MessageBoxButtons.YesNo) != DialogResult.Yes) return;
            _busy = true; _install.Enabled = false; _close.Enabled = false; _pageStart.Visible = false; _pageWork.Visible = true;
            bool noShortcut = !_shortcut.Checked; bool launch = _launch.Checked;
            Thread t = new Thread(delegate()
            {
                string error = null;
                try
                {
                    Ui(delegate { _status.Text = "در حال باز کردن فایل‌ها…"; });
                    Core.Extract(dir, delegate(int i, int n, string rel) { Ui(delegate { _bar.Maximum = n; _bar.Value = Math.Min(i, n); }); }, Log);
                    Ui(delegate { _status.Text = "در حال نصب پیش‌نیازها و آماده‌سازی (چند دقیقه طول می‌کشد)…"; _bar.Style = ProgressBarStyle.Marquee; });
                    int code = Core.RunInstall(dir, noShortcut, Log);
                    if (code != 0) error = "اسکریپت نصب با کد " + code + " پایان یافت.";
                    else if (!_o.NoRegistry) { try { Core.Register(dir); } catch { } }
                }
                catch (Exception ex) { error = ex.Message; }
                if (error != null) Log("[X] " + error);
                try { string all; lock (_sb) all = _sb.ToString(); Directory.CreateDirectory(Path.Combine(dir, "run")); File.WriteAllText(Path.Combine(dir, @"run\setup.log"), all, Encoding.UTF8); } catch { }
                Ui(delegate
                {
                    _busy = false; _done = true; _bar.Style = ProgressBarStyle.Blocks; _bar.Maximum = 100; _bar.Value = 100;
                    _close.Enabled = true; _install.Enabled = true;
                    if (error == null)
                    {
                        _status.Text = "نصب با موفقیت انجام شد."; _status.ForeColor = Color.SeaGreen; _install.Text = "پایان"; _close.Visible = false;
                        if (launch) { try { Core.Launch(dir); } catch { } }
                    }
                    else
                    {
                        _status.Text = "نصب ناموفق بود — متن زیر را ببینید (در run\\setup.log هم ذخیره شد)."; _status.ForeColor = Color.Firebrick;
                        _install.Text = "بستن"; _close.Visible = false;
                    }
                });
            });
            t.IsBackground = true; t.Start();
        }
    }

    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            Options o = new Options();
            foreach (string raw in args)
            {
                string a = raw.Trim(); string low = a.ToLowerInvariant();
                if (low == "/silent" || low == "/s" || low == "-silent") o.Silent = true;
                else if (low == "/nolaunch") o.NoLaunch = true;
                else if (low == "/noshortcut") o.NoShortcut = true;
                else if (low == "/noregistry") o.NoRegistry = true;
                else if (low == "/autostart") o.AutoStart = true;          // wizard starts installing by itself (UI tests)
                else if (low.StartsWith("/dir=")) o.Dir = a.Substring(5).Trim('"');
            }
            if (!o.Silent)
            {
                Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new Wizard(o));
                return 0;
            }
            string dir = o.Dir ?? Core.DefaultDir();
            StringBuilder sb = new StringBuilder();
            Action<string> log = delegate(string s) { lock (sb) sb.AppendLine(s); };
            int code = 1;
            try
            {
                Core.Extract(dir, delegate(int i, int n, string rel) { }, log);
                code = Core.RunInstall(dir, o.NoShortcut, log);
                if (code == 0 && !o.NoRegistry) Core.Register(dir);
                if (code == 0 && !o.NoLaunch) Core.Launch(dir);
            }
            catch (Exception ex) { log("[X] " + ex); code = 1; }
            try { Directory.CreateDirectory(Path.Combine(dir, "run")); File.WriteAllText(Path.Combine(dir, @"run\setup.log"), sb.ToString(), Encoding.UTF8); } catch { }
            return code;
        }
    }
}

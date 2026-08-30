<?php
/**
 * Plugin Name: IP htaccess Blocker
 * Plugin URI:  https://emdad.local
 * Description: مسدودسازی مستقیم IP ها در فایل .htaccess با مدیریت کامل (افزودن/حذف) از پنل تنظیمات.
 * Version:     1.2.0
 * Author:      Emdad
 * License:     GPL-2.0+
 * Text Domain: ip-htaccess-blocker
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class IHB_IP_Htaccess_Blocker {

	const OPTION_KEY = 'ihb_blocked_ips';
	const MARKER     = 'IP Htaccess Blocker';
	const NONCE      = 'ihb_manage_ips';
	const META_KEY   = 'ihb_blocked_meta';
	const LOG_KEY    = 'ihb_rest_log';
	const VERSION    = '1.2.0';

	private static $instance = null;

	public static function instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'admin_menu', array( $this, 'add_settings_page' ) );
		add_action( 'admin_init', array( $this, 'handle_actions' ) );
		add_action( 'admin_notices', array( $this, 'admin_notices' ) );
		add_action( 'rest_api_init', array( $this, 'register_rest_routes' ) );

		register_activation_hook( __FILE__, array( $this, 'on_activate' ) );
		register_deactivation_hook( __FILE__, array( $this, 'on_deactivate' ) );
	}

	/* ---------------------------------------------------------------------
	 * فعال/غیرفعال‌سازی
	 * ------------------------------------------------------------------- */

	public function on_activate() {
		// اگر لیستی از قبل وجود دارد، دوباره در htaccess بنویس.
		$this->write_htaccess( $this->get_ips() );
	}

	public function on_deactivate() {
		// هنگام غیرفعال شدن، قوانین از htaccess پاک می‌شوند (لیست در دیتابیس می‌ماند).
		$this->write_htaccess( array() );
	}

	/* ---------------------------------------------------------------------
	 * داده‌ها
	 * ------------------------------------------------------------------- */

	private function get_ips() {
		$ips = get_option( self::OPTION_KEY, array() );
		return is_array( $ips ) ? array_values( $ips ) : array();
	}

	private function save_ips( array $ips ) {
		$ips = array_values( array_unique( $ips ) );
		update_option( self::OPTION_KEY, $ips, false );
		return $this->write_htaccess( $ips );
	}

	/**
	 * اعتبارسنجی IP (IPv4 ، IPv6 و CIDR مثل 1.2.3.0/24)
	 */
	private function is_valid_ip( $ip ) {
		if ( filter_var( $ip, FILTER_VALIDATE_IP ) ) {
			return true;
		}
		// CIDR
		if ( strpos( $ip, '/' ) !== false ) {
			list( $addr, $mask ) = array_pad( explode( '/', $ip, 2 ), 2, '' );
			if ( ! ctype_digit( $mask ) ) {
				return false;
			}
			$mask = (int) $mask;
			if ( filter_var( $addr, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4 ) ) {
				return $mask >= 0 && $mask <= 32;
			}
			if ( filter_var( $addr, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6 ) ) {
				return $mask >= 0 && $mask <= 128;
			}
		}
		return false;
	}

	/* ---------------------------------------------------------------------
	 * نوشتن در htaccess
	 * ------------------------------------------------------------------- */

	private function get_htaccess_path() {
		if ( ! function_exists( 'get_home_path' ) ) {
			require_once ABSPATH . 'wp-admin/includes/file.php';
		}
		return get_home_path() . '.htaccess';
	}

	public function is_htaccess_writable() {
		$path = $this->get_htaccess_path();
		if ( file_exists( $path ) ) {
			return wp_is_writable( $path );
		}
		return wp_is_writable( dirname( $path ) );
	}

	/**
	 * قوانین بین مارکرهای پلاگین در htaccess نوشته می‌شوند
	 * و هیچ بخش دیگری از فایل دست نمی‌خورد.
	 */
	private function write_htaccess( array $ips ) {
		if ( ! function_exists( 'insert_with_markers' ) ) {
			require_once ABSPATH . 'wp-admin/includes/misc.php';
		}
		if ( ! function_exists( 'get_home_path' ) ) {
			require_once ABSPATH . 'wp-admin/includes/file.php';
		}

		$path = $this->get_htaccess_path();

		if ( ! $this->is_htaccess_writable() ) {
			return false;
		}

		$lines = array();

		if ( ! empty( $ips ) ) {
			// آپاچی 2.4 به بالا
			$lines[] = '<IfModule mod_authz_core.c>';
			$lines[] = "\t<RequireAll>";
			$lines[] = "\t\tRequire all granted";
			foreach ( $ips as $ip ) {
				$lines[] = "\t\tRequire not ip " . $ip;
			}
			$lines[] = "\t</RequireAll>";
			$lines[] = '</IfModule>';
			// آپاچی 2.2 (سرورهای قدیمی)
			$lines[] = '<IfModule !mod_authz_core.c>';
			$lines[] = "\torder allow,deny";
			foreach ( $ips as $ip ) {
				// در نحو قدیمی، CIDR پشتیبانی می‌شود
				$lines[] = "\tdeny from " . $ip;
			}
			$lines[] = "\tallow from all";
			$lines[] = '</IfModule>';
		}

		return insert_with_markers( $path, self::MARKER, $lines );
	}

	/* ---------------------------------------------------------------------
	 * فرم‌ها و اکشن‌ها
	 * ------------------------------------------------------------------- */

	public function handle_actions() {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}
		if ( empty( $_POST['ihb_action'] ) && empty( $_GET['ihb_action'] ) ) {
			return;
		}

		$redirect = admin_url( 'options-general.php?page=ihb-settings' );

		// افزودن IP
		if ( isset( $_POST['ihb_action'] ) && 'add' === $_POST['ihb_action'] ) {
			check_admin_referer( self::NONCE );

			$raw   = isset( $_POST['ihb_new_ips'] ) ? wp_unslash( $_POST['ihb_new_ips'] ) : '';
			$input = preg_split( '/[\s,;]+/', $raw, -1, PREG_SPLIT_NO_EMPTY );

			$ips     = $this->get_ips();
			$added   = 0;
			$invalid = array();

			foreach ( $input as $ip ) {
				$ip = trim( $ip );
				if ( ! $this->is_valid_ip( $ip ) ) {
					$invalid[] = $ip;
					continue;
				}
				if ( ! in_array( $ip, $ips, true ) ) {
					$ips[] = $ip;
					$added++;
				}
			}

			$ok = $this->save_ips( $ips );

			$args = array( 'ihb_added' => $added );
			if ( ! empty( $invalid ) ) {
				$args['ihb_invalid'] = rawurlencode( implode( ',', array_slice( $invalid, 0, 10 ) ) );
			}
			if ( false === $ok ) {
				$args['ihb_werr'] = 1;
			}
			wp_safe_redirect( add_query_arg( $args, $redirect ) );
			exit;
		}

		// حذف یک IP
		if ( isset( $_GET['ihb_action'] ) && 'delete' === $_GET['ihb_action'] && isset( $_GET['ip'] ) ) {
			check_admin_referer( self::NONCE );

			$ip  = wp_unslash( $_GET['ip'] );
			$ips = array_filter(
				$this->get_ips(),
				function ( $item ) use ( $ip ) {
					return $item !== $ip;
				}
			);
			$ok = $this->save_ips( $ips );

			$args = array( 'ihb_deleted' => 1 );
			if ( false === $ok ) {
				$args['ihb_werr'] = 1;
			}
			wp_safe_redirect( add_query_arg( $args, $redirect ) );
			exit;
		}

		// حذف همه
		if ( isset( $_POST['ihb_action'] ) && 'delete_all' === $_POST['ihb_action'] ) {
			check_admin_referer( self::NONCE );

			$ok   = $this->save_ips( array() );
			$args = array( 'ihb_cleared' => 1 );
			if ( false === $ok ) {
				$args['ihb_werr'] = 1;
			}
			wp_safe_redirect( add_query_arg( $args, $redirect ) );
			exit;
		}
	}

	public function admin_notices() {
		if ( ! isset( $_GET['page'] ) || 'ihb-settings' !== $_GET['page'] ) {
			return;
		}

		if ( isset( $_GET['ihb_added'] ) ) {
			$n = (int) $_GET['ihb_added'];
			if ( $n > 0 ) {
				printf(
					'<div class="notice notice-success is-dismissible"><p>%s</p></div>',
					esc_html( sprintf( '%d آی‌پی با موفقیت مسدود شد.', $n ) )
				);
			}
		}
		if ( isset( $_GET['ihb_invalid'] ) ) {
			printf(
				'<div class="notice notice-warning is-dismissible"><p>%s <code>%s</code></p></div>',
				'موارد زیر IP معتبر نبودند و نادیده گرفته شدند:',
				esc_html( rawurldecode( wp_unslash( $_GET['ihb_invalid'] ) ) )
			);
		}
		if ( isset( $_GET['ihb_deleted'] ) ) {
			echo '<div class="notice notice-success is-dismissible"><p>آی‌پی از لیست مسدودی حذف شد.</p></div>';
		}
		if ( isset( $_GET['ihb_cleared'] ) ) {
			echo '<div class="notice notice-success is-dismissible"><p>تمام آی‌پی‌های مسدود شده حذف شدند.</p></div>';
		}
		if ( isset( $_GET['ihb_werr'] ) ) {
			echo '<div class="notice notice-error"><p><strong>خطا:</strong> فایل <code>.htaccess</code> قابل نوشتن نیست. لیست در دیتابیس ذخیره شد اما در htaccess اعمال نشد. سطح دسترسی فایل را بررسی کنید (معمولاً 644 و مالکیت وب‌سرور).</p></div>';
		}
	}


	/* ---------------------------------------------------------------------
	 * SEO Brain REST API (v1.2.0)
	 *   Base: /wp-json/seo-brain/v1/
	 *   Auth: WordPress Application Password (Basic over HTTPS) + manage_options.
	 *   Thin controller over the existing blocker (save_ips / is_valid_ip /
	 *   write_htaccess) - no duplicated blocking logic.
	 * ------------------------------------------------------------------- */

	public function register_rest_routes() {
		register_rest_route( 'seo-brain/v1', '/status', array(
			'methods'             => 'GET',
			'callback'            => array( $this, 'rest_status' ),
			'permission_callback' => array( $this, 'rest_can_manage' ),
		) );
		register_rest_route( 'seo-brain/v1', '/security/blocked', array(
			'methods'             => 'GET',
			'callback'            => array( $this, 'rest_blocked' ),
			'permission_callback' => array( $this, 'rest_can_manage' ),
		) );
		register_rest_route( 'seo-brain/v1', '/security/block-ip', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'rest_block_ip' ),
			'permission_callback' => array( $this, 'rest_can_manage' ),
		) );
		register_rest_route( 'seo-brain/v1', '/security/unblock-ip', array(
			'methods'             => 'POST',
			'callback'            => array( $this, 'rest_unblock_ip' ),
			'permission_callback' => array( $this, 'rest_can_manage' ),
		) );
	}

	public function rest_can_manage() {
		return current_user_can( 'manage_options' );
	}

	// API accepts single IPv4/IPv6 only (no CIDR/hostname) - stricter than the admin panel.
	private function rest_valid_single_ip( $ip ) {
		return (bool) filter_var( $ip, FILTER_VALIDATE_IP );
	}

	private function get_meta() {
		$meta = get_option( self::META_KEY, array() );
		return is_array( $meta ) ? $meta : array();
	}

	private function save_meta( array $meta ) {
		update_option( self::META_KEY, $meta, false );
	}

	private function rest_log( $action, $ip, $ok, $note = '' ) {
		$log   = get_option( self::LOG_KEY, array() );
		$log   = is_array( $log ) ? $log : array();
		$log[] = array(
			'action' => $action,
			'ip'     => $ip,
			'ok'     => (bool) $ok,
			'note'   => (string) $note,
			'user'   => wp_get_current_user()->user_login,
			'at'     => gmdate( 'c' ),
		);
		update_option( self::LOG_KEY, array_slice( $log, -200 ), false );
	}

	public function rest_status() {
		return rest_ensure_response( array(
			'connected'      => true,
			'plugin'         => 'seo-brain',
			'plugin_version' => self::VERSION,
			'site'           => wp_parse_url( home_url(), PHP_URL_HOST ),
			'writable'       => $this->is_htaccess_writable(),
			'count'          => count( $this->get_ips() ),
		) );
	}

	public function rest_blocked() {
		$meta  = $this->get_meta();
		$items = array();
		foreach ( $this->get_ips() as $ip ) {
			$m       = isset( $meta[ $ip ] ) && is_array( $meta[ $ip ] ) ? $meta[ $ip ] : array();
			$items[] = array(
				'ip'         => $ip,
				'reason'     => isset( $m['reason'] ) ? (string) $m['reason'] : null,
				'blocked_at' => isset( $m['blocked_at'] ) ? (string) $m['blocked_at'] : null,
				'expires_at' => null,
				'status'     => 'blocked',
			);
		}
		return rest_ensure_response( array( 'items' => $items ) );
	}

	public function rest_block_ip( WP_REST_Request $request ) {
		$ip     = trim( sanitize_text_field( (string) $request->get_param( 'ip' ) ) );
		$reason = sanitize_text_field( (string) $request->get_param( 'reason' ) );

		if ( '' === $ip || ! $this->rest_valid_single_ip( $ip ) ) {
			$this->rest_log( 'block', $ip, false, 'invalid ip' );
			return new WP_Error( 'invalid_ip', 'IP address is not a valid single IPv4/IPv6.', array( 'status' => 400 ) );
		}

		$ips = $this->get_ips();
		if ( in_array( $ip, $ips, true ) ) {
			$this->rest_log( 'block', $ip, true, 'already blocked' );
			return rest_ensure_response( array( 'success' => true, 'ip' => $ip, 'status' => 'already_blocked' ) );
		}

		$ips[] = $ip;
		$ok    = $this->save_ips( $ips );

		$meta        = $this->get_meta();
		$meta[ $ip ] = array(
			'reason'     => '' !== $reason ? $reason : null,
			'blocked_at' => gmdate( 'c' ),
			'actor'      => 'seo-brain',
		);
		$this->save_meta( $meta );
		$this->rest_log( 'block', $ip, false !== $ok, false !== $ok ? '' : 'htaccess not writable' );

		if ( false === $ok ) {
			return new WP_Error( 'htaccess_not_writable', 'IP saved to the list but .htaccess is not writable.', array( 'status' => 500 ) );
		}
		return rest_ensure_response( array( 'success' => true, 'ip' => $ip, 'status' => 'blocked' ) );
	}

	public function rest_unblock_ip( WP_REST_Request $request ) {
		$ip = trim( sanitize_text_field( (string) $request->get_param( 'ip' ) ) );

		if ( '' === $ip || ! $this->rest_valid_single_ip( $ip ) ) {
			$this->rest_log( 'unblock', $ip, false, 'invalid ip' );
			return new WP_Error( 'invalid_ip', 'IP address is not valid.', array( 'status' => 400 ) );
		}

		$before = $this->get_ips();
		if ( ! in_array( $ip, $before, true ) ) {
			$this->rest_log( 'unblock', $ip, true, 'already unblocked' );
			return rest_ensure_response( array( 'success' => true, 'ip' => $ip, 'status' => 'already_unblocked' ) );
		}

		$ips = array_values( array_filter( $before, function ( $item ) use ( $ip ) {
			return $item !== $ip;
		} ) );
		$ok = $this->save_ips( $ips );

		$meta = $this->get_meta();
		unset( $meta[ $ip ] );
		$this->save_meta( $meta );
		$this->rest_log( 'unblock', $ip, false !== $ok );

		if ( false === $ok ) {
			return new WP_Error( 'htaccess_not_writable', 'IP removed from the list but .htaccess is not writable.', array( 'status' => 500 ) );
		}
		return rest_ensure_response( array( 'success' => true, 'ip' => $ip, 'status' => 'unblocked' ) );
	}

	/* ---------------------------------------------------------------------
	 * صفحه تنظیمات
	 * ------------------------------------------------------------------- */

	public function add_settings_page() {
		add_options_page(
			'مسدودسازی IP',
			'مسدودسازی IP',
			'manage_options',
			'ihb-settings',
			array( $this, 'render_settings_page' )
		);
	}

	public function render_settings_page() {
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( 'دسترسی ندارید.' );
		}

		$ips          = $this->get_ips();
		$writable     = $this->is_htaccess_writable();
		$current_ip   = isset( $_SERVER['REMOTE_ADDR'] ) ? sanitize_text_field( wp_unslash( $_SERVER['REMOTE_ADDR'] ) ) : '';
		$base_url     = admin_url( 'options-general.php?page=ihb-settings' );
		?>
		<div class="wrap">
			<h1>مسدودسازی IP در htaccess</h1>

			<?php if ( ! $writable ) : ?>
				<div class="notice notice-error">
					<p><strong>هشدار:</strong> فایل <code>.htaccess</code> قابل نوشتن نیست؛ تغییرات اعمال نخواهد شد.</p>
				</div>
			<?php endif; ?>

			<p>
				IP فعلی شما: <code><?php echo esc_html( $current_ip ); ?></code>
				— مراقب باشید IP خودتان را مسدود نکنید!
			</p>

			<h2>افزودن IP جدید</h2>
			<form method="post" action="">
				<?php wp_nonce_field( self::NONCE ); ?>
				<input type="hidden" name="ihb_action" value="add">
				<p>
					<textarea name="ihb_new_ips" rows="4" cols="50" class="large-text code" dir="ltr"
						placeholder="203.0.113.15&#10;198.51.100.0/24&#10;2001:db8::1"></textarea>
				</p>
				<p class="description">
					هر IP در یک خط (یا جدا شده با کاما/فاصله). فرمت‌های IPv4، IPv6 و بازه CIDR (مثل <code dir="ltr">1.2.3.0/24</code>) پشتیبانی می‌شود.
				</p>
				<?php submit_button( 'مسدود کن' ); ?>
			</form>

			<h2>لیست IP های مسدود شده (<?php echo count( $ips ); ?>)</h2>

			<?php if ( empty( $ips ) ) : ?>
				<p>هیچ IP مسدودی وجود ندارد.</p>
			<?php else : ?>
				<table class="widefat striped" style="max-width:600px">
					<thead>
						<tr>
							<th>#</th>
							<th>آدرس IP</th>
							<th style="width:100px">عملیات</th>
						</tr>
					</thead>
					<tbody>
						<?php foreach ( $ips as $i => $ip ) : ?>
							<?php
							$del_url = wp_nonce_url(
								add_query_arg(
									array(
										'ihb_action' => 'delete',
										'ip'         => rawurlencode( $ip ),
									),
									$base_url
								),
								self::NONCE
							);
							?>
							<tr>
								<td><?php echo (int) $i + 1; ?></td>
								<td><code dir="ltr"><?php echo esc_html( $ip ); ?></code></td>
								<td>
									<a href="<?php echo esc_url( $del_url ); ?>"
										class="button button-small"
										onclick="return confirm('این IP از لیست مسدودی حذف شود؟');">
										حذف
									</a>
								</td>
							</tr>
						<?php endforeach; ?>
					</tbody>
				</table>

				<form method="post" action="" style="margin-top:15px">
					<?php wp_nonce_field( self::NONCE ); ?>
					<input type="hidden" name="ihb_action" value="delete_all">
					<?php
					submit_button(
						'حذف همه',
						'delete',
						'submit',
						false,
						array( 'onclick' => "return confirm('تمام IP های مسدود شده حذف شوند؟');" )
					);
					?>
				</form>
			<?php endif; ?>

			<hr>
			<p class="description">
				قوانین بین مارکرهای <code dir="ltr"># BEGIN <?php echo esc_html( self::MARKER ); ?></code> و
				<code dir="ltr"># END <?php echo esc_html( self::MARKER ); ?></code> در فایل htaccess نوشته می‌شوند و
				بقیه محتوای فایل دست‌نخورده می‌ماند. با غیرفعال کردن پلاگین، قوانین به‌صورت خودکار پاک می‌شوند
				(لیست در دیتابیس باقی می‌ماند و با فعال‌سازی مجدد برمی‌گردد).
			</p>
		</div>
		<?php
	}
}

IHB_IP_Htaccess_Blocker::instance();

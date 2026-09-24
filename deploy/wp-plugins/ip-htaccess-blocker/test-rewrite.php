<?php
/* Standalone PHP 7.4 regression check for the exact-IP rewrite fallback. */
define( 'ABSPATH', __DIR__ . '/' );
function add_action() {}
function register_activation_hook() {}
function register_deactivation_hook() {}
function get_home_path() { return $GLOBALS['test_dir'] . '/'; }
function wp_is_writable() { return true; }
function insert_with_markers( $path, $marker, $lines ) {
	$GLOBALS['rendered'] = $lines;
	if ( $GLOBALS['write_ok'] ) {
		file_put_contents( $path, file_get_contents( $path ) . "\n# BEGIN $marker\n" . implode( "\n", $lines ) . "\n# END $marker\n" );
	}
	return $GLOBALS['write_ok'];
}
function update_option() { $GLOBALS['option_writes']++; }
require __DIR__ . '/ip-htaccess-blocker.php';

$plugin = IHB_IP_Htaccess_Blocker::instance();
$GLOBALS['test_dir'] = sys_get_temp_dir() . '/ihb-block-test-' . getmypid();
mkdir( $GLOBALS['test_dir'] );
$test_path = get_home_path() . '.htaccess';
file_put_contents( $test_path, "# BEGIN EAD PERMANENT ACCESS\nRewriteEngine On\nRewriteRule ^_ead_blocked\\.php$ - [END]\n# END EAD PERMANENT ACCESS\n# BEGIN EAD CUSTOM 403\nErrorDocument 403 /_ead_blocked.php\n# END EAD CUSTOM 403\n# BEGIN EAD 403 FILE ACCESS\n<Files \"_ead_blocked.php\">\nRequire all granted\n</Files>\n# END EAD 403 FILE ACCESS\n<IfModule mod_rewrite.c>\nRewriteRule . /index.php [L]\n</IfModule>\n" );
$write = new ReflectionMethod( $plugin, 'write_htaccess' );
$write->setAccessible( true );
$save = new ReflectionMethod( $plugin, 'save_ips' );
$save->setAccessible( true );
$GLOBALS['write_ok'] = true;
$GLOBALS['option_writes'] = 0;
$write->invoke( $plugin, array( '78.129.155.177', '2001:db8::5', '192.0.2.0/24' ) );
$rules = implode( "\n", $GLOBALS['rendered'] );
$file_rules = file_get_contents( $test_path );
if ( strpos( $file_rules, 'ErrorDocument 403 /_ead_blocked.php' ) === false || strpos( $file_rules, 'RewriteRule ^_ead_blocked\\.php$ - [END]' ) === false || strpos( $file_rules, '<Files "_ead_blocked.php">' ) === false ) {
	fwrite( STDERR, "Custom error document must survive plugin rewrites\n" );
	exit( 1 );
}
if ( ! ( strpos( $file_rules, '# END EAD PERMANENT ACCESS' ) < strpos( $file_rules, '# BEGIN IP Htaccess Blocker' ) && strpos( $file_rules, '# BEGIN IP Htaccess Blocker' ) < strpos( $file_rules, 'RewriteRule . /index.php [L]' ) ) ) {
	fwrite( STDERR, "Block marker must precede WordPress rewrite rules\n" );
	exit( 1 );
}
foreach ( array(
	'RewriteCond %{REMOTE_ADDR} ^78\\.129\\.155\\.177$ [OR]',
	'RewriteCond %{REMOTE_ADDR} ^2001\\:db8\\:\:5$',
	'RewriteRule ^ - [F,L]',
	'Require not ip 192.0.2.0/24',
) as $expected ) {
	if ( strpos( $rules, $expected ) === false ) {
		fwrite( STDERR, "Missing rule: $expected\n" );
		exit( 1 );
	}
}
if ( strpos( $rules, 'RewriteCond %{REMOTE_ADDR} ^192' ) !== false ) {
	fwrite( STDERR, "CIDR must not be rendered as an exact-IP regex\n" );
	exit( 1 );
}
$GLOBALS['write_ok'] = false;
if ( $save->invoke( $plugin, array( '203.0.113.10' ) ) !== false || $GLOBALS['option_writes'] !== 0 ) {
	fwrite( STDERR, "Failed htaccess write must not update blocked option\n" );
	exit( 1 );
}
echo "rewrite regression checks passed\n";
unlink( $test_path );
rmdir( $GLOBALS['test_dir'] );

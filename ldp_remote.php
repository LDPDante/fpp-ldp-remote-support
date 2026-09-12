<?php
// LDP Remote Support - customer-facing connect/disconnect page.
// Rendered inside the FPP UI (wrap=1). $pluginName / FPP settings helpers are preset.
if (!isset($pluginName)) { $pluginName = "fpp-ldp-remote-support"; }
$TS  = "/usr/bin/tailscale";
$PLUGIN_DIR = "/home/fpp/media/plugins/fpp-ldp-remote-support";

// --- "click a link" actions: ?enable=1 connects, ?disable=1 disconnects ---
$did = '';
if (isset($_GET['enable'])) {
    WriteSettingToFile("RemoteSupportEnabled", "True", $pluginName);
    @shell_exec("nohup $PLUGIN_DIR/commands/apply.sh > /dev/null 2>&1 &");
    $did = 'enable';
} elseif (isset($_GET['disable'])) {
    WriteSettingToFile("RemoteSupportEnabled", "False", $pluginName);
    @shell_exec("nohup $PLUGIN_DIR/commands/apply.sh > /dev/null 2>&1 &");
    $did = 'disable';
}

$raw = @shell_exec("$TS status --json 2>/dev/null");
$st  = json_decode($raw, true);
$backend   = is_array($st) ? ($st['BackendState'] ?? 'Unknown') : 'Unknown';
$selfIP    = is_array($st) ? ($st['Self']['TailscaleIPs'][0] ?? '') : '';
$connected = ($backend === 'Running' && $selfIP !== '');

// this page's URL without the action params (for the auto-refresh / links)
$base = "plugin.php?plugin=" . urlencode($pluginName) . "&page=ldp_remote.php";
?>
<div class="row"><div class="col-md-12">
 <div class="card mt-2">
  <div class="card-header"><b>LDP Remote Support</b></div>
  <div class="card-body">

  <?php if ($did === 'enable' && !$connected): ?>
    <div class="alert alert-info">Connecting to L&nbsp;Designs&nbsp;Plus support&hellip; this takes a few seconds.</div>
    <script>setTimeout(function(){ location.href='<?php echo $base; ?>'; }, 8000);</script>
  <?php endif; ?>

  <?php if ($connected): ?>
    <div class="alert alert-success d-flex align-items-center justify-content-between flex-wrap gap-2">
      <span><b>&#10003; Connected to L&nbsp;Designs&nbsp;Plus support.</b> We can now help you remotely.</span>
      <a class="btn btn-outline-secondary btn-sm" href="<?php echo $base; ?>&disable=1">Disconnect</a>
    </div>
    <p class="text-muted mb-0 small">Support address: <code><?php echo htmlspecialchars($selfIP); ?></code></p>
  <?php elseif ($did !== 'enable'): ?>
    <p class="mb-3">Connect this controller to L&nbsp;Designs&nbsp;Plus so we can help set it up and fix issues remotely. It&rsquo;s optional, and you can disconnect anytime.</p>
    <a class="btn btn-primary btn-lg" href="<?php echo $base; ?>&enable=1">Connect to LDP Support</a>
  <?php endif; ?>

  <div class="alert alert-light border mt-3 mb-0 small">
    When connected, this controller reaches L&nbsp;Designs&nbsp;Plus over a private, encrypted link. It does <u>not</u> expose anything else on your home network, and it stays off until you press <b>Connect</b>.
  </div>

  </div>
 </div>
</div></div>

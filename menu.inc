<?php
// Registers the plugin's menu entry. FPP presets $plugin (repoName) and $menu
// (the current menu section: status|content|output|help).
$menuEntries = Array(
    Array( 'text' => 'LDP Remote Support', 'type' => 'status', 'page' => 'ldp_remote.php', 'wrap' => 1 )
);

foreach ($menuEntries as $entry) {
    if ($entry['type'] != $menu) continue;
    if (preg_match('/^http.?:\/\//', $entry['page'])) {
        printf("<li><a href='%s' target='_blank'>%s</a></li>\n", $entry['page'], $entry['text']);
    } else {
        $nopage = (isset($entry['wrap']) && $entry['wrap'] == 0) ? '&nopage=1' : '';
        printf("<li><a href='plugin.php?plugin=%s&page=%s%s'>%s</a></li>\n",
            $plugin, $entry['page'], $nopage, $entry['text']);
    }
}
?>

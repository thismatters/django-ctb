<script lang="ts">
  import favicon from "$lib/assets/favicon.svg";

  let { children } = $props();
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
  <!-- SMUI Styles -->
  <link rel="stylesheet" href="/smui.css" />
  <!-- Hint where we get fonts from. -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />

  <!-- Roboto, and Roboto Mono fonts -->
  <link
    href="https://fonts.googleapis.com/css2?family=Roboto+Mono:ital@0;1&family=Roboto:ital,wght@0,100;0,300;0,400;0,500;0,700;0,900;1,100;1,300;1,400;1,500;1,700;1,900&display=swap"
    rel="stylesheet"
  />
  <!-- Material Icons fonts -->
  <link
    href="https://fonts.googleapis.com/css2?family=Material+Icons&display=swap"
    rel="stylesheet"
  />
</svelte:head>

{@render children()}

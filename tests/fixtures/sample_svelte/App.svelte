<script>
  import { onMount } from 'svelte';
  import Counter from './Counter.svelte';

  let count = 0;
  let message = '';

  // Increment the counter
  function increment() {
    count += 1;
  }

  function reset() {
    count = 0;
    message = '';
  }

  async function fetchData(url) {
    const res = await fetch(url);
    return res.json();
  }

  onMount(() => {
    message = 'Component mounted';
  });
</script>

<main>
  <h1>Count: {count}</h1>
  <button on:click={increment}>+1</button>
  <button on:click={reset}>Reset</button>
  <Counter />
</main>

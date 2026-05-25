<script module>
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import TableFilterOptionsList from "$lib/components/TableFilterOptionsList.svelte";

  const { Story } = defineMeta({
    title: "Library/TableFilterOptionsList",
    component: TableFilterOptionsList,
    tags: ["autodocs"],
    argTypes: {},
    args: {},
    decorators: [],
    render: templateSnippet
  });
</script>

{#snippet templateSnippet(args)}
  <TableFilterOptionsList {...args} bind:selectedOptions={args.selectedOptions} />
  <p>Selected Options: {args.selectedOptions}</p>
{/snippet}

<Story
  name="Flat Options"
  args={{
    options: ["one", "two", "thr3e"],
    field_name: "test",
    supports_exact: true,
    supports_isnull: false,
    choice_options: null,
    selectedOptions: ["one"]
  }}
/>

<Story
  name="Flat Options isnull"
  args={{
    options: ["one", "two", "thr3e"],
    field_name: "test",
    supports_exact: true,
    supports_isnull: true,
    choice_options: null,
    selectedOptions: ["two", "thr3e"]
  }}
/>

<Story
  name="Choice Options"
  args={{
    options: null,
    field_name: "test",
    supports_exact: true,
    supports_isnull: false,
    choice_options: [
      { value: "1", label: "one" },
      { value: "2", label: "two" },
      { value: "3", label: "thr3e" }
    ],
    selectedOptions: ["3"]
  }}
/>

<Story
  name="Choice Options isnull"
  args={{
    options: null,
    field_name: "test",
    supports_exact: true,
    supports_isnull: true,
    choice_options: [
      { value: "1", label: "one" },
      { value: "2", label: "two" },
      { value: "3", label: "thr3e" }
    ],
    selectedOptions: [null]
  }}
/>

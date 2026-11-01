# Testing DevLens

What to do when you have been invited to try the DevLens demo. The demo runs on a server that is
switched on for test sessions, so it is only reachable while a session is open.

## Getting in

You need two things from the owner, sent privately: the site's address and an access key.

1. Open the address. You see the DevLens access page.
2. Enter the access key. Your browser stays signed in to the site for 30 days.
3. To ask questions or look at commit changes, click **Sign in with GitHub** in the header. Any
   GitHub account works. DevLens reads your GitHub profile and email address, nothing else: it
   gets no access to your repositories.

If the page does not load at all, the demo is probably switched off. Ask the owner to start it.

## What to try

1. **Analyze a repository.** Paste a public GitHub URL on the home page, for example
   `https://github.com/pallets/itsdangerous`. A small repository takes a minute or two, and the
   steps show their progress as they run. Repositories over 8,000 source files are turned away.
2. **Overview.** The architecture summary, language mix, contributors, code health (long
   functions linked to their lines on GitHub), hotspots, the import explorer, and the file tree.
3. **Chat.** Ask how something works, for example "How are tokens signed?". Answers cite the
   files and lines they come from; the small numbers open those lines on GitHub. Earlier chats are
   listed on the left. You can stop an answer or copy it.
4. **Changes.** Pick an analyzed commit to see each changed file's diff, the security-sensitive
   lines with how serious they are, and the files that import the change, drawn as rings. You can
   ask questions about the commit too.
5. **Share.** On a repository page, **Share** makes a read-only link to its Overview that works
   for 7 days without a key or a sign-in. **Stop sharing** turns it off.
6. **Dark mode.** The moon button in the header. Your browser remembers the choice.

## Good to know

- You can make 50 requests an hour while signed in (analyses, questions), and 10 without signing
  in. At the limit, an analysis says "Rate limit exceeded" and the chat says how long to wait;
  either way, try again later in the hour.
- Answers describe the commit that was analyzed. If the repository changed since, analyze it
  again to pick up the new code.
- Hotspots need an analysis made after 2026-11-01. On an older one, the card says to analyze the
  repository again.
- To get comments on your own pull requests, add the Action described in the
  [README](README.md#what-it-does) to your repository. It runs in your CI and does not need this
  demo.

## Reporting a problem

Note the address of the page, what you did, and what you expected. A screenshot helps. Send it to
the owner or open an issue on the repository.

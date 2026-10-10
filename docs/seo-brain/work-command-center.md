# Work command center

`/dashboard/work` is the cross-site execution workspace. It uses the existing `work_items` ledger instead of keeping separate copies of tasks in reports, content planning and the dashboard. Every work item belongs to one site and can have a team, owner, due date, priority, estimated hours, source URL and verification note. Active and verified stages require an owner and due date; blocked work requires a reason; verified work requires evidence in its verification note.

## Views

| View | Purpose |
| --- | --- |
| Command | Urgent queue, owner workload, site action recommendations and recent changes |
| Sheet | Cross-site task inventory with status, owner, team, priority and due date |
| Kanban | Same tasks grouped by execution stage |
| Timeline | Due date load for the next 21 days and a chronological delivery list |
| Responsibility graph | Site → task, task → owner and task → team relationships, capped at 35 visible tasks |
| Teams | Team directory, member assignments and current open work |
| Projects | Site ownership, milestones, task hierarchy, scheduled work and logged time |

The main dashboard includes a live work pulse and opens this workspace. Each site report still has its existing detailed work tab and shares the same records. The portfolio's next recommended action can be converted into an unassigned task for review; the interface avoids an obvious duplicate while an open task with the same title exists.

The overview API (`GET /api/v1/work/overview`) provides filtered summary totals, a capped list of tasks, grouping by site/owner/team/status, due dates and recent work events. The UI says when a filter matches more than the 500 returned tasks. Counts come from saved work items; estimated hours are planning estimates, not tracked time. The graph represents execution responsibility, not the SEO knowledge graph.

Teams live in `panel_teams`, and users and work items reference them through `team_id`. Creating and editing teams, assigning members and mutating tasks require an administrator. Analysts can read the workspace, while call-center operators remain restricted to call-center. Work events store the acting panel username when an individual session made the change; trusted service jobs appear as system actions. The panel audit also records the route and changed field names.

The migration sequence is `0029_work_command_center.sql`, `0030_work_event_actor.sql`, then `0031_project_execution.sql`. Back up the database before applying migrations in any environment. A deeper feature and release analysis is in `project-management-research-2026-10-05.md`.

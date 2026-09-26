-- Annual reports, shareholding patterns, and governance announcements are
-- attributed evidence but are not financial-statement scopes.

alter table public.documents
    drop constraint documents_reporting_scope_check,
    add constraint documents_reporting_scope_check
        check (reporting_scope in (
            'consolidated', 'standalone', 'group', 'bank', 'not_applicable'
        ));

import { Route, Routes } from 'react-router';

import { CHANGE_PASSWORD_PATH, RequireAuth } from './auth/guards';
import { Layout } from './components/Layout';
import { JobsPage } from './pages/admin/JobsPage';
import { LdapPage } from './pages/admin/LdapPage';
import { StoragePage } from './pages/admin/StoragePage';
import { UsersPage } from './pages/admin/UsersPage';
import { ChangePasswordPage } from './pages/ChangePasswordPage';
import { HomePage } from './pages/HomePage';
import { LoginPage } from './pages/LoginPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ProfilePage } from './pages/ProfilePage';

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="login" element={<LoginPage />} />
        <Route
          path={CHANGE_PASSWORD_PATH.slice(1)}
          element={
            <RequireAuth allowPendingPasswordChange>
              <ChangePasswordPage />
            </RequireAuth>
          }
        />
        <Route
          path="profile"
          element={
            <RequireAuth>
              <ProfilePage />
            </RequireAuth>
          }
        />
        <Route
          path="admin/users"
          element={
            <RequireAuth admin>
              <UsersPage />
            </RequireAuth>
          }
        />
        <Route
          path="admin/ldap"
          element={
            <RequireAuth admin>
              <LdapPage />
            </RequireAuth>
          }
        />
        <Route
          path="admin/storage"
          element={
            <RequireAuth admin>
              <StoragePage />
            </RequireAuth>
          }
        />
        <Route
          path="admin/jobs"
          element={
            <RequireAuth admin>
              <JobsPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

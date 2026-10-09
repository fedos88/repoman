import { Center, Loader } from '@mantine/core';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';

import { useMe } from '../api/auth';
import { NotFoundPage } from '../pages/NotFoundPage';

export const CHANGE_PASSWORD_PATH = '/change-password';

function FullPageLoader() {
  return (
    <Center py={80}>
      <Loader />
    </Center>
  );
}

type GuardProps = {
  children: ReactNode;
  /** Admin role required. Access control here is UX only; the backend enforces it. */
  admin?: boolean;
  /** Allowed while a password change is pending. */
  allowPendingPasswordChange?: boolean;
};

export function RequireAuth({
  children,
  admin = false,
  allowPendingPasswordChange = false,
}: GuardProps) {
  const location = useLocation();
  const { data: me, isPending } = useMe();

  if (isPending) {
    return <FullPageLoader />;
  }
  if (!me) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (me.must_change_password && !allowPendingPasswordChange) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  }
  if (admin && !me.is_admin) {
    return <NotFoundPage />;
  }
  return children;
}

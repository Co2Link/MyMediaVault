import "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      entraOid: string | null;
      isAdmin: boolean;
      name?: string | null;
      email?: string | null;
      image?: string | null;
    };
  }

  interface User {
    entraOid: string | null;
    isAdmin: boolean;
  }
}

declare module "@auth/core/jwt" {
  interface JWT {
    entraOid?: string | null;
    roles?: string[];
    picture?: string;
  }
}

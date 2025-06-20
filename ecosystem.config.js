module.exports = {
    apps: [
      // {
      //   name: "frontend",
      //   script: "npm run dev",
      //   cwd: "frontend_vue",
      //   env: {
      //     NODE_ENV: "development"
      //   }
      // },
      {
        name: "faster-whisper",
        script: "python",
        args: "faster-whisper.py --serve --host 0.0.0.0 --port 8002",
        cwd: "backend",
        env: {
          PYTHONPATH: "."
        }
      },
      {
        name: "llm",
        script: "python",
        args: "llm.py",
        cwd: "backend",
        env: {
          PYTHONPATH: "."
        }
      },
      {
        name: "backend",
        script: "python",
        args: "app.py",
        cwd: "backend",
        env: {
          PYTHONPATH: "."
        }
      },
      // {
      //   name: "backend",
      //   script: "node",
      //   args: "backend.js",
      //   cwd: "backend",
      //   env: {
      //     NODE_ENV: "development"
      //   }
      // }
    ]
  };

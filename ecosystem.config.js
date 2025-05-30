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
        args: "faster-whisper.py --serve",
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
        script: "node",
        args: "backend.js",
        cwd: "backend",
        env: {
          NODE_ENV: "development"
        }
      }
    ]
  };